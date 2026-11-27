"""
All read-only. Everything here is scoped to the caller's company via RLS
the same way every other read has been all along — no company_id
filtering needed in these queries, the database does it.
"""
import calendar
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles
from ..models import RentalUnit, Lease, RentReceipt, MaintenanceRequest, AnnualCheckin, SecurityDeposit, Tenant, LeaseTenant, User
from ..schemas import DashboardSummaryOut, OverdueLeaseOut

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
VIEW_ROLES = ("company_admin", "staff")


@router.get("/summary", response_model=DashboardSummaryOut)
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VIEW_ROLES)),
):
    total_units = db.query(RentalUnit).filter(RentalUnit.is_deleted.is_(False)).count()

    occupied_units = (
        db.query(func.count(func.distinct(Lease.rental_unit_id)))
        .filter(Lease.status == "active")
        .scalar()
    ) or 0

    active_leases_q = db.query(Lease).filter(Lease.status == "active")
    active_leases = active_leases_q.count()
    total_monthly_rent = float(
        db.query(func.coalesce(func.sum(Lease.monthly_rent), 0))
        .filter(Lease.status == "active")
        .scalar()
    )

    today = date.today()
    month_start = today.replace(day=1)
    rent_collected_this_month = float(
        db.query(func.coalesce(func.sum(RentReceipt.amount), 0))
        .filter(RentReceipt.is_deleted.is_(False),
                RentReceipt.date_received >= month_start, RentReceipt.date_received <= today)
        .scalar()
    )

    maintenance_rows = (
        db.query(MaintenanceRequest.status, func.count(MaintenanceRequest.id))
        .filter(MaintenanceRequest.is_deleted.is_(False))
        .group_by(MaintenanceRequest.status)
        .all()
    )
    maintenance_by_status = {status: count for status, count in maintenance_rows}

    checkins_total = db.query(AnnualCheckin).count()
    checkins_acked = db.query(AnnualCheckin).filter(AnnualCheckin.acknowledged_at.isnot(None)).count()
    checkins_overdue = (
        db.query(AnnualCheckin)
        .filter(AnnualCheckin.acknowledged_at.is_(None), AnnualCheckin.due_date < today)
        .count()
    )

    deposits_held = float(
        db.query(func.coalesce(func.sum(SecurityDeposit.amount_collected), 0))
        .filter(SecurityDeposit.status.in_(["collected", "held"]))
        .scalar()
    )

    return DashboardSummaryOut(
        total_units=total_units,
        occupied_units=occupied_units,
        vacant_units=total_units - occupied_units,
        active_leases=active_leases,
        total_monthly_rent=total_monthly_rent,
        rent_collected_this_month=rent_collected_this_month,
        maintenance_by_status=maintenance_by_status,
        annual_checkins_total=checkins_total,
        annual_checkins_acknowledged=checkins_acked,
        annual_checkins_overdue=checkins_overdue,
        security_deposits_held=deposits_held,
    )


@router.get("/overdue-rent", response_model=list[OverdueLeaseOut])
def overdue_rent(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*VIEW_ROLES)),
):
    """
    SIMPLIFIED, worth stating plainly: a lease counts as "overdue" here if
    (a) today is past this month's due_day_of_month for that lease, and
    (b) total rent_receipts recorded THIS MONTH for that lease add up to
    less than the monthly_rent amount.

    This does NOT track multi-month arrears (a lease that's been behind
    for 3 months shows the same as one behind for 3 days), doesn't handle
    a due_day_of_month that doesn't exist in the current month (e.g. 31
    in a 30-day month — clamped to the month's last real day), and
    treats any partial payment as "not yet caught up" rather than
    crediting it properly against a running balance. A real arrears
    ledger would need its own design, not just this summary query.
    """
    today = date.today()
    month_start = today.replace(day=1)
    last_day_this_month = calendar.monthrange(today.year, today.month)[1]

    active_leases = db.query(Lease).filter(Lease.status == "active").all()

    results = []
    for lease in active_leases:
        effective_due_day = min(lease.due_day_of_month, last_day_this_month)
        if today.day <= effective_due_day:
            continue

        paid_this_month = float(
            db.query(func.coalesce(func.sum(RentReceipt.amount), 0))
            .filter(RentReceipt.lease_id == lease.id,
                     RentReceipt.is_deleted.is_(False),
                     RentReceipt.date_received >= month_start,
                     RentReceipt.date_received <= today)
            .scalar()
        )
        if paid_this_month >= float(lease.monthly_rent):
            continue

        unit = db.query(RentalUnit).filter(RentalUnit.id == lease.rental_unit_id).first()
        tenant_names = [
            t.name for t in
            db.query(Tenant)
            .join(LeaseTenant, LeaseTenant.tenant_id == Tenant.id)
            .filter(LeaseTenant.lease_id == lease.id)
            .all()
        ]

        results.append(OverdueLeaseOut(
            lease_id=lease.id,
            rental_unit_id=lease.rental_unit_id,
            unit_reference=unit.unit_reference if unit else "(unknown)",
            monthly_rent=float(lease.monthly_rent),
            due_day_of_month=lease.due_day_of_month,
            amount_paid_this_month=paid_this_month,
            tenant_names=tenant_names,
        ))

    return results
