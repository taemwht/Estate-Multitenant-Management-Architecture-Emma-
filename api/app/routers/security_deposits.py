import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import SecurityDeposit, Lease, User
from ..schemas import SecurityDepositCreate, SecurityDepositUpdate, SecurityDepositOut
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for, ensure_lease_visible

router = APIRouter(prefix="/security-deposits", tags=["security-deposits"])

# INFERRED, same as tenants: no explicit row for this in the PRD's Roles
# & Permissions table. Using the same roles as rent receipts/rental
# units — flag if this should differ.
WRITE_ROLES = ("company_admin", "staff")
VALID_STATUSES = ("collected", "held", "returned", "deducted")


@router.post("", response_model=SecurityDepositOut, status_code=status.HTTP_201_CREATED)
def create_security_deposit(
    body: SecurityDepositCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    lease = db.query(Lease).filter(Lease.id == body.lease_id).first()
    if not lease:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease not found")

    deposit = SecurityDeposit(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        lease_id=body.lease_id,
        amount_collected=body.amount_collected,
    )
    db.add(deposit)
    try:
        db.flush()
    except IntegrityError as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This lease already has a security deposit record.",
        )

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="security_deposit",
        entity_id=deposit.id,
        after_state=body.model_dump(mode="json"),
    )

    result = SecurityDepositOut.model_validate(deposit)
    db.commit()
    return result


@router.get("", response_model=list[SecurityDepositOut])
def list_security_deposits(
    lease_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    query = db.query(SecurityDeposit)
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        if not scope.lease_ids:
            return []
        query = query.filter(SecurityDeposit.lease_id.in_(scope.lease_ids))
    if lease_id:
        query = query.filter(SecurityDeposit.lease_id == lease_id)
    return query.all()


@router.get("/{deposit_id}", response_model=SecurityDepositOut)
def get_security_deposit(
    deposit_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    deposit = db.query(SecurityDeposit).filter(SecurityDeposit.id == deposit_id).first()
    if not deposit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security deposit not found")
    ensure_lease_visible(tenant_scope_for(db, current_user), deposit.lease_id, "Security deposit not found")
    return deposit


@router.patch("/{deposit_id}", response_model=SecurityDepositOut)
def update_security_deposit(
    deposit_id: uuid.UUID,
    body: SecurityDepositUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    deposit = db.query(SecurityDeposit).filter(SecurityDeposit.id == deposit_id).first()
    if not deposit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Security deposit not found")

    if body.status is not None and body.status not in VALID_STATUSES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"status must be one of {VALID_STATUSES}")

    before = SecurityDepositOut.model_validate(deposit).model_dump(mode="json")
    changes = body.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(deposit, field, value)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="update",
        entity_type="security_deposit",
        entity_id=deposit.id,
        before_state=before,
        after_state=changes,
    )

    result = SecurityDepositOut.model_validate(deposit)
    db.commit()
    return result
