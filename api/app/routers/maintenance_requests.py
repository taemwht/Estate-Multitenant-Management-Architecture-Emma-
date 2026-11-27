import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import MaintenanceRequest, MaintenancePhoto, MaintenanceLog, RentalUnit, Contractor, ContractorCompany, Tenant, User
from ..schemas import MaintenanceRequestCreate, MaintenanceRequestUpdate, MaintenanceRequestOut, MaintenanceLogCreate, MaintenanceLogOut
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for

router = APIRouter(prefix="/maintenance-requests", tags=["maintenance-requests"])

CREATE_ROLES = ("company_admin", "staff", "tenant")
MANAGE_ROLES = ("company_admin", "staff")
VALID_STATUSES = ("Submitted", "Scheduled", "In Progress", "On Hold", "Completed", "Verified", "Cancelled")
VALID_PRIORITIES = ("emergency", "high", "normal", "low")


def _to_out(db: Session, req: MaintenanceRequest) -> MaintenanceRequestOut:
    photos = [
        p.file_url for p in
        db.query(MaintenancePhoto).filter(MaintenancePhoto.maintenance_request_id == req.id).all()
    ]
    data = MaintenanceRequestOut.model_validate(req).model_dump()
    data["photo_urls"] = photos
    return MaintenanceRequestOut(**data)


def _tenant_owns(req: MaintenanceRequest, scope, user: User) -> bool:
    """A tenant sees only the requests they reported (or submitted from
    their own login) — not every request filed against the building."""
    return (
        (scope.tenant_id is not None and req.reported_by_tenant_id == scope.tenant_id)
        or req.submitted_by == user.id
    )


def _get_request(db: Session, request_id, user: User) -> MaintenanceRequest:
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
    scope = tenant_scope_for(db, user)
    if not req or (scope is not None and not _tenant_owns(req, scope, user)):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance request not found")
    return req


@router.post("", response_model=MaintenanceRequestOut, status_code=status.HTTP_201_CREATED)
def create_maintenance_request(
    body: MaintenanceRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*CREATE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    if body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"priority must be one of {VALID_PRIORITIES}")

    scope = tenant_scope_for(db, current_user)
    reported_by_tenant_id = body.reported_by_tenant_id

    unit = db.query(RentalUnit).filter(RentalUnit.id == body.rental_unit_id).first()
    if not unit or (scope is not None and unit.id not in scope.active_unit_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rental unit not found")

    if scope is not None:
        # Tenants file requests as themselves, for a unit they rent.
        if scope.tenant_id is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail="No tenant record is linked to your account.")
        if reported_by_tenant_id is not None and reported_by_tenant_id != scope.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                                 detail="Tenants can only report requests as themselves.")
        reported_by_tenant_id = scope.tenant_id
    elif reported_by_tenant_id is not None:
        tenant = db.query(Tenant).filter(
            Tenant.id == body.reported_by_tenant_id, Tenant.is_deleted.is_(False)
        ).first()
        if not tenant:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")

    req = MaintenanceRequest(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        rental_unit_id=body.rental_unit_id,
        submitted_by=current_user.id,
        reported_by_tenant_id=reported_by_tenant_id,
        description=body.description,
        location_detail=body.location_detail,
        tenant_availability=body.tenant_availability,
        priority=body.priority,
        status="Submitted",
    )
    db.add(req)
    db.flush()

    for url in body.photo_urls:
        db.add(MaintenancePhoto(id=uuid.uuid4(), maintenance_request_id=req.id, file_url=url))
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="create", entity_type="maintenance_request",
        entity_id=req.id, after_state=body.model_dump(mode="json"),
    )

    result = _to_out(db, req)
    db.commit()
    return result


@router.get("", response_model=list[MaintenanceRequestOut])
def list_maintenance_requests(
    status_filter: str | None = None,
    rental_unit_id: uuid.UUID | None = None,
    assigned_contractor_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    # Default view excludes cancelled and deleted, matching the old
    # skill's "exclude cancelled/deleted unless explicitly requested"
    # rule — pass status_filter="Cancelled" explicitly to see them.
    query = db.query(MaintenanceRequest).filter(MaintenanceRequest.is_deleted.is_(False))
    if status_filter:
        query = query.filter(MaintenanceRequest.status == status_filter)
    else:
        query = query.filter(MaintenanceRequest.status != "Cancelled")
    if rental_unit_id:
        query = query.filter(MaintenanceRequest.rental_unit_id == rental_unit_id)
    if assigned_contractor_id:
        query = query.filter(MaintenanceRequest.assigned_contractor_id == assigned_contractor_id)

    priority_order = {"emergency": 0, "high": 1, "normal": 2, "low": 3}
    reqs = query.all()
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        reqs = [r for r in reqs if _tenant_owns(r, scope, current_user)]
    reqs.sort(key=lambda r: (priority_order.get(r.priority, 2), r.submitted_at or datetime.min))
    return [_to_out(db, r) for r in reqs]


@router.get("/{request_id}", response_model=MaintenanceRequestOut)
def get_maintenance_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    return _to_out(db, _get_request(db, request_id, current_user))


@router.patch("/{request_id}", response_model=MaintenanceRequestOut)
def update_maintenance_request(
    request_id: uuid.UUID,
    body: MaintenanceRequestUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance request not found")

    if body.status is not None and body.status not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"status must be one of {VALID_STATUSES}")
    if body.priority is not None and body.priority not in VALID_PRIORITIES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"priority must be one of {VALID_PRIORITIES}")

    if body.assigned_contractor_id is not None:
        linked = (
            db.query(Contractor)
            .join(ContractorCompany, ContractorCompany.contractor_id == Contractor.id)
            .filter(Contractor.id == body.assigned_contractor_id,
                     ContractorCompany.company_id == current_user.company_id,
                     ContractorCompany.is_deleted.is_(False))
            .first()
        )
        if not linked:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail="Contractor not found for this company")

    before = _to_out(db, req).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True, mode="json")
    now = datetime.now(timezone.utc)
    for field, value in changes.items():
        setattr(req, field, value)

    # Matches the old skill's real trigger: assigning a contractor AND
    # setting a scheduled_date TOGETHER auto-advances status — not just
    # setting status="Scheduled" directly (that was the actual bug in
    # the original build: it conflated "status says Scheduled" with
    # "someone is actually lined up for a real date").
    if "status" not in changes:
        contractor_set = req.assigned_contractor_id is not None
        date_set = req.scheduled_date is not None
        if contractor_set and date_set and req.status == "Submitted":
            req.status = "Scheduled"
            changes["status"] = "Scheduled"

    if changes.get("status") == "Scheduled":
        req.scheduled_at = now
    elif changes.get("status") == "In Progress":
        req.in_progress_at = now
    elif changes.get("status") == "On Hold":
        req.on_hold_at = now
    elif changes.get("status") == "Cancelled":
        req.cancelled_at = now
    elif changes.get("status") == "Completed":
        req.completed_at = now
    elif changes.get("status") == "Verified":
        req.verified_at = now
        req.verified_by = current_user.id

    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="update", entity_type="maintenance_request",
        entity_id=req.id, before_state=before, after_state=changes,
    )

    result = _to_out(db, req)
    db.commit()
    return result


@router.post("/{request_id}/verify", response_model=MaintenanceRequestOut)
def verify_maintenance_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("company_admin", "staff", "tenant")),
    actor_type: str = Depends(get_actor_type),
):
    """PRD 4.6: verification can come from either the tenant or admin/staff.
    A tenant can only verify their own request, and only once it's
    Completed (confirming the work was done)."""
    req = _get_request(db, request_id, current_user)
    if req.status == "Verified":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Already verified")
    if current_user.role == "tenant" and req.status != "Completed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail="Only a Completed request can be verified.")

    before = _to_out(db, req).model_dump(mode="json")
    req.status = "Verified"
    req.verified_at = datetime.now(timezone.utc)
    req.verified_by = current_user.id
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="verify", entity_type="maintenance_request",
        entity_id=req.id, before_state=before,
    )

    result = _to_out(db, req)
    db.commit()
    return result


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_maintenance_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """Different from Cancelled — this removes the request from default
    views entirely (logged in error/duplicate). Cancelled stays visible
    in history as "reported but didn't proceed."."""
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance request not found")

    req.is_deleted = True
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="soft_delete", entity_type="maintenance_request",
        entity_id=req.id,
    )
    db.commit()


@router.post("/{request_id}/restore", response_model=MaintenanceRequestOut)
def restore_maintenance_request(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance request not found")
    if not req.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Request is not deleted")

    req.is_deleted = False
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="restore", entity_type="maintenance_request",
        entity_id=req.id,
    )

    result = _to_out(db, req)
    db.commit()
    return result


@router.post("/{request_id}/log", response_model=MaintenanceLogOut, status_code=status.HTTP_201_CREATED)
def add_log_entry(
    request_id: uuid.UUID,
    body: MaintenanceLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*MANAGE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """No confirmation needed (matches old skill) — purely a timestamped
    touchpoint note, not a field change. If the note implies a real
    field change, that's a separate PATCH call too."""
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == request_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Maintenance request not found")

    entry = MaintenanceLog(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        maintenance_request_id=request_id,
        entry_text=body.entry_text,
        recorded_by=current_user.id,
    )
    db.add(entry)
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="log_entry", entity_type="maintenance_request",
        entity_id=request_id, after_state={"entry_text": body.entry_text},
    )

    result = MaintenanceLogOut.model_validate(entry)
    db.commit()
    return result


@router.get("/{request_id}/log", response_model=list[MaintenanceLogOut])
def list_log_entries(
    request_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    _get_request(db, request_id, current_user)
    return (
        db.query(MaintenanceLog)
        .filter(MaintenanceLog.maintenance_request_id == request_id)
        .order_by(MaintenanceLog.created_at)
        .all()
    )
