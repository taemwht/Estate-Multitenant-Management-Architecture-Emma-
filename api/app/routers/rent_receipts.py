import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import RentReceipt, Lease, User
from ..schemas import RentReceiptCreate, RentReceiptUpdate, RentReceiptOut
from ..scoping import STAFF_AND_TENANT_ROLES, tenant_scope_for, ensure_lease_visible

router = APIRouter(prefix="/rent-receipts", tags=["rent-receipts"])

# PRD roles table lists this one explicitly (unlike tenants/security
# deposits): Super Admin / Company Admin / Staff = yes, Contractor /
# Tenant = no. Matches the WRITE_ROLES pattern used elsewhere.
WRITE_ROLES = ("company_admin", "staff")
VALID_METHODS = ("check", "cash", "other")


def _validate_amounts(method, amount, late_fee):
    if method is not None and method not in VALID_METHODS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                             detail=f"method must be one of {VALID_METHODS}")
    if amount is not None and amount < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="amount cannot be negative")
    if late_fee is not None and late_fee < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="late_fee cannot be negative")


def _get_receipt(db: Session, receipt_id, current_user: User) -> RentReceipt:
    receipt = db.query(RentReceipt).filter(RentReceipt.id == receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rent receipt not found")
    ensure_lease_visible(tenant_scope_for(db, current_user), receipt.lease_id, "Rent receipt not found")
    return receipt


@router.post("", response_model=RentReceiptOut, status_code=status.HTTP_201_CREATED)
def create_rent_receipt(
    body: RentReceiptCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    _validate_amounts(body.method, body.amount, body.late_fee)

    # Explicit check rather than relying on the FK alone — same reasoning
    # as leases validating rental_unit_id: RLS-scoped lookup means a
    # cross-company lease_id correctly looks like "not found," not a
    # leaked detail about another company's data.
    lease = db.query(Lease).filter(Lease.id == body.lease_id).first()
    if not lease:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lease not found")

    receipt = RentReceipt(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        lease_id=body.lease_id,
        amount=body.amount,
        date_received=body.date_received,
        method=body.method,
        late_fee=body.late_fee,
        recorded_by=current_user.id,
        notes=body.notes,
    )
    db.add(receipt)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="rent_receipt",
        entity_id=receipt.id,
        after_state=body.model_dump(mode="json"),
    )

    result = RentReceiptOut.model_validate(receipt)
    db.commit()
    return result


@router.get("", response_model=list[RentReceiptOut])
def list_rent_receipts(
    lease_id: uuid.UUID | None = None,
    include_deleted: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    """Soft-deleted receipts are hidden unless include_deleted=true
    (admin/staff only — tenants never see deleted entries)."""
    query = db.query(RentReceipt)
    scope = tenant_scope_for(db, current_user)
    if scope is not None:
        if not scope.lease_ids:
            return []
        query = query.filter(RentReceipt.lease_id.in_(scope.lease_ids))
        include_deleted = False
    if not include_deleted:
        query = query.filter(RentReceipt.is_deleted.is_(False))
    if lease_id:
        query = query.filter(RentReceipt.lease_id == lease_id)
    return query.order_by(RentReceipt.date_received.desc()).all()


@router.get("/{receipt_id}", response_model=RentReceiptOut)
def get_rent_receipt(
    receipt_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_AND_TENANT_ROLES)),
):
    receipt = _get_receipt(db, receipt_id, current_user)
    if current_user.role == "tenant" and receipt.is_deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rent receipt not found")
    return receipt


@router.patch("/{receipt_id}", response_model=RentReceiptOut)
def update_rent_receipt(
    receipt_id: uuid.UUID,
    body: RentReceiptUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """For correcting a data-entry error on a payment — NOT for logging a
    new payment (POST /rent-receipts for that)."""
    receipt = _get_receipt(db, receipt_id, current_user)
    _validate_amounts(body.method, body.amount, body.late_fee)

    changes = body.model_dump(exclude_unset=True)
    for required in ("amount", "date_received", "method", "late_fee"):
        if required in changes and changes[required] is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                 detail=f"{required} cannot be set to null")

    before = RentReceiptOut.model_validate(receipt).model_dump(mode="json")
    for field, value in changes.items():
        setattr(receipt, field, value)
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="update", entity_type="rent_receipt",
        entity_id=receipt.id, before_state=before,
        after_state=body.model_dump(exclude_unset=True, mode="json"),
    )

    result = RentReceiptOut.model_validate(receipt)
    db.commit()
    return result


@router.delete("/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_rent_receipt(
    receipt_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """For a payment logged in error (duplicate, wrong lease). Deleted
    receipts stop counting toward rent status, arrears and the dashboard."""
    receipt = _get_receipt(db, receipt_id, current_user)
    receipt.is_deleted = True
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="soft_delete", entity_type="rent_receipt",
        entity_id=receipt.id,
    )
    db.commit()


@router.post("/{receipt_id}/restore", response_model=RentReceiptOut)
def restore_rent_receipt(
    receipt_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    receipt = _get_receipt(db, receipt_id, current_user)
    if not receipt.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Receipt is not deleted")

    receipt.is_deleted = False
    db.flush()

    write_audit_log(
        db, company_id=current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="restore", entity_type="rent_receipt",
        entity_id=receipt.id,
    )

    result = RentReceiptOut.model_validate(receipt)
    db.commit()
    return result
