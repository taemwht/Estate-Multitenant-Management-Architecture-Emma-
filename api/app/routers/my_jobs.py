"""
The contractor's view: only the maintenance jobs assigned to them.

A contractor login has no company, so RLS shows it nothing. These
endpoints read under the bypass but filter hard to jobs whose
assigned_contractor_id is a contractor record linked to this login, in a
company that still uses that contractor (link not removed). Anything else
is a 404, the same as a row that doesn't exist.

A contractor can see the job and where it is, move it along
(In Progress / On Hold / Completed) and add notes. Verifying the work,
cancelling, re-assigning and everything about rent and tenants stays with
the company.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db, super_admin_session
from ..deps import get_actor_type, require_roles
from ..models import Company, Contractor, ContractorCompany, MaintenanceLog, MaintenanceRequest, RentalUnit, User
from ..schemas import JobOut, JobUpdate, MaintenanceLogCreate, MaintenanceLogOut

router = APIRouter(prefix="/my-jobs", tags=["contractor"])

CONTRACTOR_STATUSES = ("In Progress", "On Hold", "Completed")
OPEN_FOR_CONTRACTOR = ("Scheduled", "In Progress", "On Hold")
STAMP = {"In Progress": "in_progress_at", "On Hold": "on_hold_at", "Completed": "completed_at"}


def _jobs_query(db: Session, user: User):
    return (
        db.query(MaintenanceRequest)
        .join(Contractor, Contractor.id == MaintenanceRequest.assigned_contractor_id)
        .join(ContractorCompany, (ContractorCompany.contractor_id == Contractor.id)
              & (ContractorCompany.company_id == MaintenanceRequest.company_id))
        .filter(Contractor.user_id == user.id,
                Contractor.is_deleted.is_(False),
                ContractorCompany.is_deleted.is_(False),
                MaintenanceRequest.is_deleted.is_(False),
                MaintenanceRequest.status != "Cancelled")
    )


def _to_job(db: Session, req: MaintenanceRequest) -> JobOut:
    unit = db.query(RentalUnit).filter(RentalUnit.id == req.rental_unit_id).first()
    company = db.query(Company).filter(Company.id == req.company_id).first()
    address = ", ".join(x for x in [unit and unit.address_line1, unit and unit.city] if x) if unit else ""
    return JobOut(
        id=req.id, company_name=company.name if company else "", address=address,
        unit_reference=unit.unit_reference if unit else None,
        description=req.description, location_detail=req.location_detail,
        tenant_availability=req.tenant_availability, priority=req.priority,
        status=req.status, scheduled_date=req.scheduled_date,
    )


def _get_job(db: Session, job_id, user: User) -> MaintenanceRequest:
    req = _jobs_query(db, user).filter(MaintenanceRequest.id == job_id).first()
    if not req:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return req


@router.get("", response_model=list[JobOut])
def list_my_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("contractor")),
):
    order = {"emergency": 0, "high": 1, "normal": 2, "low": 3}
    with super_admin_session(db):
        reqs = _jobs_query(db, current_user).all()
        reqs.sort(key=lambda r: (r.status in ("Completed", "Verified"), order.get(r.priority, 2),
                                 r.scheduled_date or datetime.max.date()))
        return [_to_job(db, r) for r in reqs]


@router.patch("/{job_id}", response_model=JobOut)
def update_my_job(
    job_id: uuid.UUID,
    body: JobUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("contractor")),
    actor_type: str = Depends(get_actor_type),
):
    if body.status not in CONTRACTOR_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"status must be one of {CONTRACTOR_STATUSES}")
    with super_admin_session(db):
        req = _get_job(db, job_id, current_user)
        if req.status not in OPEN_FOR_CONTRACTOR:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"A {req.status} job can't be changed by the contractor.")
        before = req.status
        req.status = body.status
        setattr(req, STAMP[body.status], datetime.now(timezone.utc))
        db.flush()
        write_audit_log(
            db, company_id=req.company_id, actor_id=current_user.id, actor_type=actor_type,
            action="update", entity_type="maintenance_request", entity_id=req.id,
            before_state={"status": before}, after_state={"status": body.status},
        )
        db.flush()  # write the audit row while the bypass is still on (RLS checks it on insert)
        result = _to_job(db, req)
    db.commit()
    return result


@router.get("/{job_id}/log", response_model=list[MaintenanceLogOut])
def list_my_job_log(
    job_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("contractor")),
):
    with super_admin_session(db):
        _get_job(db, job_id, current_user)
        rows = (db.query(MaintenanceLog)
                .filter(MaintenanceLog.maintenance_request_id == job_id)
                .order_by(MaintenanceLog.created_at).all())
        return [MaintenanceLogOut.model_validate(r) for r in rows]


@router.post("/{job_id}/log", response_model=MaintenanceLogOut, status_code=status.HTTP_201_CREATED)
def add_my_job_note(
    job_id: uuid.UUID,
    body: MaintenanceLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("contractor")),
    actor_type: str = Depends(get_actor_type),
):
    with super_admin_session(db):
        req = _get_job(db, job_id, current_user)
        entry = MaintenanceLog(id=uuid.uuid4(), company_id=req.company_id,
                               maintenance_request_id=req.id, entry_text=body.entry_text,
                               recorded_by=current_user.id)
        db.add(entry)
        db.flush()
        write_audit_log(
            db, company_id=req.company_id, actor_id=current_user.id, actor_type=actor_type,
            action="log_entry", entity_type="maintenance_request", entity_id=req.id,
            after_state={"entry_text": body.entry_text},
        )
        db.flush()
        result = MaintenanceLogOut.model_validate(entry)
    db.commit()
    return result
