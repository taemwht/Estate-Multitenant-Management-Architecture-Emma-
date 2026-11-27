import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db, super_admin_session
from ..deps import require_roles, get_actor_type
from ..models import Contractor, ContractorCompany, MaintenanceRequest, User
from ..schemas import ContractorCreate, ContractorUpdate, ContractorOut, LoginCreate
from ..security import hash_password
from ..scoping import STAFF_ROLES, ADMIN_ROLES

router = APIRouter(prefix="/contractors", tags=["contractors"])
WRITE_ROLES = ("company_admin", "staff")
VALID_TRADES = (
    "plumber", "electrician", "hvac", "handyman", "roofer",
    "appliance", "locksmith", "pest_control", "landscaping",
    "general", "other",
)

# How sharing works (migration 008):
#   - A contractor row can be linked to several companies through
#     contractor_companies. The company that created it
#     (created_by_company_id) is the only one that can edit the shared
#     record; RLS enforces the same rule.
#   - "Deleting" a contractor is per-company: it sets is_deleted on the
#     caller's own contractor_companies link, so the contractor disappears
#     for that company only and stays available to the others.


def _link(db: Session, contractor_id, company_id) -> Optional[ContractorCompany]:
    if company_id is None:
        return None
    return (
        db.query(ContractorCompany)
        .filter(ContractorCompany.contractor_id == contractor_id,
                ContractorCompany.company_id == company_id)
        .first()
    )


def _to_out(db: Session, contractor: Contractor, user: User) -> ContractorOut:
    """is_deleted reflects what the CALLER sees: their own link's delete
    flag (or the global flag, which only super admin sets)."""
    out = ContractorOut.model_validate(contractor)
    out.has_login = contractor.user_id is not None
    link = _link(db, contractor.id, user.company_id)
    if link is not None and link.is_deleted:
        out.is_deleted = True
    return out


def _get_visible(db: Session, contractor_id, user: User) -> Contractor:
    contractor = db.query(Contractor).filter(Contractor.id == contractor_id).first()
    if not contractor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
    return contractor


@router.post("", response_model=ContractorOut, status_code=status.HTTP_201_CREATED)
def create_contractor(
    body: ContractorCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """
    No super-admin bypass needed any more: the contractors INSERT/SELECT
    policies allow a row whose created_by_company_id is the caller's own
    company, so the insert and the contractor_companies link both run
    under normal company scoping.
    """
    if body.trade not in VALID_TRADES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"trade must be one of {VALID_TRADES}")

    contractor_id = uuid.uuid4()
    contractor = Contractor(
        id=contractor_id,
        created_by_company_id=current_user.company_id,
        **body.model_dump(),
    )
    db.add(contractor)
    db.flush()

    db.add(ContractorCompany(contractor_id=contractor_id, company_id=current_user.company_id))
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="create", entity_type="contractor",
        entity_id=contractor_id, after_state=body.model_dump(),
    )

    result = _to_out(db, contractor, current_user)
    db.commit()
    return result


@router.get("", response_model=list[ContractorOut])
def list_contractors(
    trade: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_ROLES)),
):
    query = db.query(Contractor).filter(Contractor.is_deleted.is_(False))
    if current_user.company_id is not None:
        # Only contractors this company has an active (not removed) link to.
        query = (
            query.join(ContractorCompany, ContractorCompany.contractor_id == Contractor.id)
            .filter(ContractorCompany.company_id == current_user.company_id,
                    ContractorCompany.is_deleted.is_(False))
        )
    if trade:
        query = query.filter(Contractor.trade == trade)
    return [_to_out(db, c, current_user) for c in query.order_by(Contractor.trade, Contractor.name).all()]


@router.get("/{contractor_id}", response_model=ContractorOut)
def get_contractor(
    contractor_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_ROLES)),
):
    return _to_out(db, _get_visible(db, contractor_id, current_user), current_user)


@router.patch("/{contractor_id}", response_model=ContractorOut)
def update_contractor(
    contractor_id: uuid.UUID,
    body: ContractorUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    contractor = _get_visible(db, contractor_id, current_user)
    if contractor.created_by_company_id != current_user.company_id:
        # RLS would silently match 0 rows here; say why instead.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This contractor is shared and was created by another company; "
                   "only that company can edit the contractor's details.",
        )
    if body.trade is not None and body.trade not in VALID_TRADES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"trade must be one of {VALID_TRADES}")

    before = _to_out(db, contractor, current_user).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True, mode="json")
    for field, value in changes.items():
        setattr(contractor, field, value)
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="update", entity_type="contractor",
        entity_id=contractor.id, before_state=before, after_state=changes,
    )

    result = _to_out(db, contractor, current_user)
    db.commit()
    return result


@router.delete("/{contractor_id}", status_code=status.HTTP_200_OK)
def delete_contractor(
    contractor_id: uuid.UUID,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """
    Removes the contractor from THIS company only (soft-deletes the
    company's contractor_companies link). Other companies sharing the
    contractor are unaffected.

    Can return a WARNING instead of deleting: if the contractor is
    assigned to any of this company's active (non-terminal) maintenance
    requests and force=false, returns 200 with the active request list —
    the old skill's warn-then-force pattern. Pass ?force=true to proceed;
    those assignments are then cleared.
    """
    contractor = _get_visible(db, contractor_id, current_user)
    link = _link(db, contractor.id, current_user.company_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")

    # RLS limits this to the caller's company's requests.
    active_requests = (
        db.query(MaintenanceRequest)
        .filter(MaintenanceRequest.assigned_contractor_id == contractor_id,
                 MaintenanceRequest.is_deleted.is_(False),
                 MaintenanceRequest.status.in_(["Submitted", "Scheduled", "In Progress", "On Hold"]))
        .all()
    )

    if active_requests and not force:
        return {
            "warning": "active_assignment_attached",
            "contractor_id": str(contractor_id),
            "active_requests": [
                {"id": str(r.id), "description": r.description, "status": r.status}
                for r in active_requests
            ],
        }

    for r in active_requests:
        r.assigned_contractor_id = None

    link.is_deleted = True
    db.flush()

    # Capture BEFORE commit: after commit SQLAlchemy expires these objects
    # and re-reading r.id would SELECT outside this transaction's RLS
    # context.
    cleared_ids = [str(r.id) for r in active_requests]

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="soft_delete", entity_type="contractor",
        entity_id=contractor.id,
        after_state={"cleared_assignments": cleared_ids},
    )
    db.commit()
    return {"deleted": True, "cleared_assignments": cleared_ids}


@router.post("/{contractor_id}/restore", response_model=ContractorOut)
def restore_contractor(
    contractor_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    contractor = _get_visible(db, contractor_id, current_user)
    link = _link(db, contractor.id, current_user.company_id)
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor not found")
    if not link.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contractor is not deleted")

    link.is_deleted = False
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="restore", entity_type="contractor",
        entity_id=contractor.id,
    )

    result = _to_out(db, contractor, current_user)
    db.commit()
    return result


@router.post("/{contractor_id}/login", response_model=ContractorOut, status_code=status.HTTP_201_CREATED)
def create_contractor_login(
    contractor_id: uuid.UUID,
    body: LoginCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """Give a contractor a login. Only the company that created the
    contractor can do this. The login has no company of its own: a
    contractor signs in and sees only the jobs assigned to them, in
    whichever companies use them (GET /my-jobs)."""
    if len(body.password) < 8:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="Password must be at least 8 characters")
    contractor = _get_visible(db, contractor_id, current_user)
    if contractor.created_by_company_id != current_user.company_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only the company that added this contractor can give them a login.")
    if contractor.user_id is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This contractor already has a login")

    company_id = current_user.company_id
    # A company-less user row is only insertable (and visible) under the bypass.
    with super_admin_session(db, company_id=str(company_id)):
        if db.query(User.id).filter(User.email == body.email).first():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
        user = User(id=uuid.uuid4(), company_id=None, role="contractor",
                    email=body.email, password_hash=hash_password(body.password))
        db.add(user)
        db.flush()
        contractor.user_id = user.id
        db.flush()

    write_audit_log(
        db, company_id=company_id, actor_id=current_user.id,
        actor_type=actor_type, action="create_login", entity_type="contractor",
        entity_id=contractor.id, after_state={"email": body.email},
    )
    result = _to_out(db, contractor, current_user)
    db.commit()
    return result
