import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import AnnualCheckin, Lease, LeaseTenant, Tenant, User
from ..schemas import AnnualCheckinCreate, AnnualCheckinAcknowledge, AnnualCheckinOut
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for, ensure_lease_visible

router = APIRouter(prefix="/annual-checkins", tags=["annual-checkins"])
WRITE_ROLES = ("company_admin", "staff")
VALID_HAZARDS = ("co_detector", "smoke_detector", "mold", "lead_paint", "asbestos")


@router.post("", response_model=AnnualCheckinOut, status_code=status.HTTP_201_CREATED)
def create_annual_checkin(
    body: AnnualCheckinCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    if body.hazard_type not in VALID_HAZARDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"hazard_type must be one of {VALID_HAZARDS}")

    lease = db.query(Lease).filter(Lease.id == body.lease_id).first()
    if not lease:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease not found")

    checkin = AnnualCheckin(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        **body.model_dump(),
    )
    db.add(checkin)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A check-in for this lease/year/hazard_type combination already exists.",
        )

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="annual_checkin",
        entity_id=checkin.id,
        after_state=body.model_dump(mode="json"),
    )

    result = AnnualCheckinOut.model_validate(checkin)
    db.commit()
    return result


@router.get("", response_model=list[AnnualCheckinOut])
def list_annual_checkins(
    lease_id: uuid.UUID | None = None,
    year: int | None = None,
    unacknowledged_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    query = db.query(AnnualCheckin)
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        if not scope.lease_ids:
            return []
        query = query.filter(AnnualCheckin.lease_id.in_(scope.lease_ids))
    if lease_id:
        query = query.filter(AnnualCheckin.lease_id == lease_id)
    if year:
        query = query.filter(AnnualCheckin.year == year)
    if unacknowledged_only:
        query = query.filter(AnnualCheckin.acknowledged_at.is_(None))
    return query.order_by(AnnualCheckin.due_date).all()


@router.post("/run-reminder-sweep")
def trigger_reminder_sweep(
    current_user: User = Depends(require_roles("super_admin", *WRITE_ROLES)),
):
    """
    Manual trigger for testing — the real job runs automatically once a
    day across all companies (see app/scheduler.py). From here, a
    company admin/staff user only sweeps their OWN company's check-ins;
    only super_admin can trigger the system-wide sweep.
    """
    from ..scheduler import run_reminder_sweep
    if current_user.role == "super_admin":
        count = run_reminder_sweep()
    else:
        count = run_reminder_sweep(company_id=str(current_user.company_id))
    return {"reminders_sent": count}


@router.get("/{checkin_id}", response_model=AnnualCheckinOut)
def get_annual_checkin(
    checkin_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    checkin = db.query(AnnualCheckin).filter(AnnualCheckin.id == checkin_id).first()
    if not checkin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annual check-in not found")
    ensure_lease_visible(tenant_scope_for(db, current_user), checkin.lease_id, "Annual check-in not found")
    return checkin


@router.post("/{checkin_id}/acknowledge", response_model=AnnualCheckinOut)
def acknowledge_annual_checkin(
    checkin_id: uuid.UUID,
    body: AnnualCheckinAcknowledge,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("company_admin", "staff", "tenant")),
    actor_type: str = Depends(get_actor_type),
):
    checkin = db.query(AnnualCheckin).filter(AnnualCheckin.id == checkin_id).first()
    if not checkin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annual check-in not found")
    scope = tenant_scope_for(db, current_user)
    ensure_lease_visible(scope, checkin.lease_id, "Annual check-in not found")
    if checkin.acknowledged_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already acknowledged")

    if scope is not None and body.tenant_id is not None and body.tenant_id != scope.tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                             detail="Tenants can only acknowledge for themselves.")

    if body.tenant_id is not None and scope is None:
        # admin/staff acknowledging on a tenant's behalf. Check the tenant
        # through the RLS-scoped session (the FK alone would accept another
        # company's tenant id) and that they're actually on this lease.
        on_lease = (
            db.query(Tenant)
            .join(LeaseTenant, LeaseTenant.tenant_id == Tenant.id)
            .filter(Tenant.id == body.tenant_id, Tenant.is_deleted.is_(False),
                    LeaseTenant.lease_id == checkin.lease_id)
            .first()
        )
        if not on_lease:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail="Tenant not found on this check-in's lease")
        tenant_id = body.tenant_id
    else:
        # tenant acknowledging for themselves — look up their own tenant
        # record via the user_id link (tenants.user_id, set at signup)
        own_tenant = db.query(Tenant).filter(Tenant.user_id == current_user.id).first()
        if not own_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No tenant record linked to your account — an admin/staff user must "
                       "acknowledge on your behalf by passing tenant_id explicitly.",
            )
        tenant_id = own_tenant.id

    checkin.acknowledged_by = tenant_id
    checkin.acknowledged_at = datetime.now(timezone.utc)
    if body.evidence_file:
        checkin.evidence_file = body.evidence_file
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="acknowledge",
        entity_type="annual_checkin",
        entity_id=checkin.id,
        after_state={"tenant_id": str(tenant_id)},
    )

    result = AnnualCheckinOut.model_validate(checkin)
    db.commit()
    return result
