import uuid
import calendar
from datetime import date as date_type
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import Lease, LeaseTenant, RentalUnit, Tenant, RentRateHistory, RentReceipt, User
from ..schemas import LeaseCreate, LeaseUpdate, LeaseOut, RentChangeCreate, RentRateHistoryOut, RentRateHistoryUpdate, RentStatusOut, ArrearsOut, MonthlyArrearsEntry
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for, ensure_lease_visible

router = APIRouter(prefix="/leases", tags=["leases"])

WRITE_ROLES = ("company_admin", "staff")


def _to_lease_out(db: Session, lease: Lease) -> LeaseOut:
    tenant_ids = [
        row.tenant_id for row in
        db.query(LeaseTenant).filter(LeaseTenant.lease_id == lease.id).all()
    ]
    data = LeaseOut.model_validate(lease).model_dump()
    data["tenant_ids"] = tenant_ids
    return LeaseOut(**data)


def _get_lease(db: Session, lease_id, current_user: User) -> Lease:
    """RLS-scoped lookup, plus the tenant-role check: a tenant only sees
    leases they're on. Either miss is a plain 404."""
    lease = db.query(Lease).filter(Lease.id == lease_id).first()
    if not lease:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease not found")
    ensure_lease_visible(tenant_scope_for(db, current_user), lease.id, "Lease not found")
    return lease


def _validate_due_day(due_day):
    if due_day is not None and not 1 <= due_day <= 31:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="due_day_of_month must be between 1 and 31")


def _latest_rate_row(db: Session, lease_id):
    db.flush()  # autoflush is off; make pending history edits visible to the query
    return (
        db.query(RentRateHistory)
        .filter(RentRateHistory.lease_id == lease_id, RentRateHistory.is_deleted.is_(False))
        .order_by(RentRateHistory.effective_date.desc(), RentRateHistory.created_at.desc())
        .first()
    )


def _sync_lease_rate(db: Session, lease: Lease) -> None:
    """Keep lease.monthly_rent / due_day_of_month equal to the most recent
    (by effective_date) non-deleted rent_rate_history row. Called after
    every history change, so editing or deleting the latest entry, or
    recording a back-dated change, can't leave the lease showing a
    different rate from its history."""
    latest = _latest_rate_row(db, lease.id)
    if latest is not None:
        lease.monthly_rent = latest.monthly_rent
        lease.due_day_of_month = latest.due_day_of_month


@router.post("", response_model=LeaseOut, status_code=status.HTTP_201_CREATED)
def create_lease(
    body: LeaseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    _validate_due_day(body.due_day_of_month)

    # Explicit visibility checks rather than relying on the FK constraint
    # alone: Postgres FK checks run with the constraint owner's
    # privileges internally and can see rows RLS would otherwise hide
    # from this session. Querying through the normal (RLS-scoped) session
    # first means "unit belongs to another company" correctly looks like
    # "unit not found" to the caller, not a leaked cross-company detail.
    unit = db.query(RentalUnit).filter(RentalUnit.id == body.rental_unit_id).first()
    if not unit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rental unit not found")

    if not body.tenant_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="At least one tenant_id is required")
    found_tenants = (
        db.query(Tenant)
        .filter(Tenant.id.in_(body.tenant_ids), Tenant.is_deleted.is_(False))
        .all()
    )
    if len(found_tenants) != len(set(body.tenant_ids)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="One or more tenant_ids not found")

    lease = Lease(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        rental_unit_id=body.rental_unit_id,
        start_date=body.start_date,
        end_date=body.end_date,
        monthly_rent=body.monthly_rent,
        due_day_of_month=body.due_day_of_month,
        security_deposit_amount=body.security_deposit_amount,
    )
    db.add(lease)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        # This is the uq_one_active_lease_per_unit partial unique index
        # from schema.sql firing — turn the raw constraint violation into
        # something a caller can actually act on.
        if "uq_one_active_lease_per_unit" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This unit already has an active lease. End the existing lease before creating a new one.",
            )
        raise

    for tenant_id in set(body.tenant_ids):
        db.add(LeaseTenant(lease_id=lease.id, tenant_id=tenant_id))

    # Every lease starts with a rent_rate_history row for its opening
    # rate, so arrears for months before the first recorded change still
    # know what the ORIGINAL rate was.
    db.add(RentRateHistory(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        lease_id=lease.id,
        monthly_rent=body.monthly_rent,
        due_day_of_month=body.due_day_of_month,
        effective_date=body.start_date,
        recorded_by=current_user.id,
    ))
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="lease",
        entity_id=lease.id,
        after_state={**body.model_dump(mode="json")},
    )

    result = _to_lease_out(db, lease)
    db.commit()
    return result


@router.get("", response_model=list[LeaseOut])
def list_leases(
    rental_unit_id: uuid.UUID | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    query = db.query(Lease)
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        if not scope.lease_ids:
            return []
        query = query.filter(Lease.id.in_(scope.lease_ids))
    if rental_unit_id:
        query = query.filter(Lease.rental_unit_id == rental_unit_id)
    if status_filter:
        query = query.filter(Lease.status == status_filter)
    leases = query.order_by(Lease.start_date.desc()).all()
    return [_to_lease_out(db, lease) for lease in leases]


@router.get("/{lease_id}", response_model=LeaseOut)
def get_lease(
    lease_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    return _to_lease_out(db, _get_lease(db, lease_id, current_user))


@router.patch("/{lease_id}", response_model=LeaseOut)
def update_lease(
    lease_id: uuid.UUID,
    body: LeaseUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    lease = _get_lease(db, lease_id, current_user)

    if body.status is not None and body.status not in ("active", "ended"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="status must be 'active' or 'ended'")
    _validate_due_day(body.due_day_of_month)

    before = _to_lease_out(db, lease).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        setattr(lease, field, value)

    # PATCH is the data-entry-fix path (a genuine change over time goes
    # through POST .../rent-changes). Correct the current history row too,
    # so the lease and its history keep agreeing.
    if "monthly_rent" in changes or "due_day_of_month" in changes:
        latest = _latest_rate_row(db, lease.id)
        if latest is not None:
            if "monthly_rent" in changes:
                latest.monthly_rent = changes["monthly_rent"]
            if "due_day_of_month" in changes:
                latest.due_day_of_month = changes["due_day_of_month"]

    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        if "uq_one_active_lease_per_unit" in str(e.orig):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This unit already has a different active lease.",
            )
        raise

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="update",
        entity_type="lease",
        entity_id=lease.id,
        before_state=before,
        after_state=changes,
    )

    result = _to_lease_out(db, lease)
    db.commit()
    return result


@router.post("/{lease_id}/rent-changes", response_model=LeaseOut)
def record_rent_change(
    lease_id: uuid.UUID,
    body: RentChangeCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """
    For a GENUINE rent change over time — not a data-entry fix (use plain
    PATCH /leases/{id} for that). Writes a permanent rent_rate_history row
    (the audit trail) and re-syncs the lease's monthly_rent /
    due_day_of_month to the most recent history entry, so the rest of the
    system keeps using the current figure. A back-dated change that's
    older than an existing entry is recorded but doesn't override it.
    """
    lease = _get_lease(db, lease_id, current_user)
    _validate_due_day(body.due_day_of_month)

    history_row = RentRateHistory(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        lease_id=lease_id,
        monthly_rent=body.monthly_rent,
        due_day_of_month=body.due_day_of_month,
        effective_date=body.effective_date,
        recorded_by=current_user.id,
    )
    db.add(history_row)
    _sync_lease_rate(db, lease)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="rent_change",
        entity_type="lease",
        entity_id=lease.id,
        after_state=body.model_dump(mode="json"),
    )

    result = _to_lease_out(db, lease)
    db.commit()
    return result


@router.get("/{lease_id}/rent-history", response_model=list[RentRateHistoryOut])
def get_rent_history(
    lease_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    _get_lease(db, lease_id, current_user)

    return (
        db.query(RentRateHistory)
        .filter(RentRateHistory.lease_id == lease_id, RentRateHistory.is_deleted.is_(False))
        .order_by(RentRateHistory.effective_date.desc())
        .all()
    )


def _get_history_row(db: Session, lease_id, history_id) -> RentRateHistory:
    row = db.query(RentRateHistory).filter(
        RentRateHistory.id == history_id, RentRateHistory.lease_id == lease_id
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rent change record not found")
    return row


@router.patch("/{lease_id}/rent-changes/{history_id}", response_model=RentRateHistoryOut)
def update_rent_change(
    lease_id: uuid.UUID,
    history_id: uuid.UUID,
    body: RentRateHistoryUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """For correcting a data-entry error on a historical rent-change
    record — NOT for recording an actual new rent change (use POST
    .../rent-changes for that)."""
    lease = _get_lease(db, lease_id, current_user)
    row = _get_history_row(db, lease_id, history_id)
    _validate_due_day(body.due_day_of_month)

    before = RentRateHistoryOut.model_validate(row).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        setattr(row, field, value)
    _sync_lease_rate(db, lease)
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="update", entity_type="rent_rate_history",
        entity_id=row.id, before_state=before, after_state=changes,
    )

    result = RentRateHistoryOut.model_validate(row)
    db.commit()
    return result


@router.delete("/{lease_id}/rent-changes/{history_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_rent_change(
    lease_id: uuid.UUID,
    history_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """For correcting a genuine error (duplicate entry) — NOT for an
    actual rent decrease, which should be a new rent-change entry to
    preserve history, same distinction the old skill made."""
    lease = _get_lease(db, lease_id, current_user)
    row = _get_history_row(db, lease_id, history_id)

    row.is_deleted = True
    _sync_lease_rate(db, lease)
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="soft_delete", entity_type="rent_rate_history",
        entity_id=row.id,
    )
    db.commit()


@router.post("/{lease_id}/rent-changes/{history_id}/restore", response_model=RentRateHistoryOut)
def restore_rent_change(
    lease_id: uuid.UUID,
    history_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    lease = _get_lease(db, lease_id, current_user)
    row = _get_history_row(db, lease_id, history_id)
    if not row.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Record is not deleted")

    row.is_deleted = False
    _sync_lease_rate(db, lease)
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="restore", entity_type="rent_rate_history",
        entity_id=row.id,
    )

    result = RentRateHistoryOut.model_validate(row)
    db.commit()
    return result


@router.get("/{lease_id}/rent-status", response_model=RentStatusOut)
def get_rent_status(
    lease_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    """
    Quick "this calendar month" snapshot — payments received this month
    against this month's rent. For the full running balance (late
    payments for earlier months, credits, multi-month arrears) use
    GET /leases/{id}/arrears.
    """
    lease = _get_lease(db, lease_id, current_user)

    today = date_type.today()
    month_start = today.replace(day=1)
    last_day_this_month = calendar.monthrange(today.year, today.month)[1]
    effective_due_day = min(lease.due_day_of_month, last_day_this_month)

    receipts_this_month = (
        db.query(RentReceipt)
        .filter(RentReceipt.lease_id == lease_id, RentReceipt.is_deleted.is_(False),
                 RentReceipt.date_received >= month_start, RentReceipt.date_received <= today)
        .all()
    )
    paid = float(sum(r.amount for r in receipts_this_month))
    late_fees = float(sum(r.late_fee for r in receipts_this_month))
    outstanding = max(0.0, float(lease.monthly_rent) - paid)
    is_overdue = today.day > effective_due_day and outstanding > 0

    return RentStatusOut(
        lease_id=lease.id,
        monthly_rent=float(lease.monthly_rent),
        due_day_of_month=lease.due_day_of_month,
        paid_this_period=paid,
        late_fee_charged_this_period=late_fees,
        outstanding=outstanding,
        is_overdue=is_overdue,
    )


@router.get("/{lease_id}/arrears", response_model=ArrearsOut)
def get_arrears(
    lease_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    """
    Running-balance arrears from the lease's start_date up to today (or
    end_date if the lease ended earlier).

    How it's computed:
      - Each month is charged the rate in effect ON THAT MONTH'S DUE DATE
        (from rent_rate_history), so a change effective mid-month applies
        from the first due date on or after it.
      - The current month is only charged once its due date has arrived —
        rent that isn't due yet isn't arrears.
      - All non-deleted payments are pooled and applied oldest month
        first. A payment for July made on August 2 pays off July, and an
        overpayment carries forward. Anything left after every charged
        month is credit_balance.
    Late fees are tracked on receipts but not charged here.
    """
    lease = _get_lease(db, lease_id, current_user)

    rate_history = (
        db.query(RentRateHistory)
        .filter(RentRateHistory.lease_id == lease_id, RentRateHistory.is_deleted.is_(False))
        .order_by(RentRateHistory.effective_date.asc(), RentRateHistory.created_at.asc())
        .all()
    )
    if not rate_history:
        # Fallback for a lease with no history rows (predates the
        # feature, or every row was soft-deleted): treat the lease's
        # current rate as constant.
        class _FallbackRate:
            effective_date = lease.start_date
            monthly_rent = lease.monthly_rent
            due_day_of_month = lease.due_day_of_month
        rate_history = [_FallbackRate()]

    def rate_on(day):
        applicable = [r for r in rate_history if r.effective_date <= day]
        return applicable[-1] if applicable else rate_history[0]

    receipts = (
        db.query(RentReceipt)
        .filter(RentReceipt.lease_id == lease_id, RentReceipt.is_deleted.is_(False))
        .all()
    )
    total_paid = sum((Decimal(r.amount) for r in receipts), Decimal("0"))

    today = date_type.today()
    end_bound = lease.end_date if (lease.end_date and lease.end_date < today) else today

    charges = []  # (year, month, due_date, expected)
    y, m = lease.start_date.year, lease.start_date.month
    while (y, m) <= (end_bound.year, end_bound.month):
        last_day = calendar.monthrange(y, m)[1]
        due_day = min(rate_on(date_type(y, m, 1)).due_day_of_month, last_day)
        due_date = date_type(y, m, due_day)
        if due_date <= today:
            charges.append((y, m, due_date, Decimal(rate_on(due_date).monthly_rent)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)

    remaining = total_paid
    breakdown = []
    total_owed = Decimal("0")
    for y, m, due_date, expected in charges:
        applied = min(remaining, expected)
        remaining -= applied
        outstanding = expected - applied
        total_owed += outstanding
        breakdown.append(MonthlyArrearsEntry(
            year=y, month=m, due_date=due_date,
            expected_rent=float(expected), paid=float(applied), outstanding=float(outstanding),
        ))

    return ArrearsOut(
        lease_id=lease.id,
        total_owed=float(total_owed),
        total_paid=float(total_paid),
        credit_balance=float(remaining),
        monthly_breakdown=breakdown,
    )
