import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import require_roles, get_actor_type
from ..models import ContractorPayment, Contractor, ContractorCompany, MaintenanceRequest, User
from ..schemas import ContractorPaymentCreate, ContractorPaymentOut
from ..scoping import STAFF_ROLES

router = APIRouter(prefix="/contractor-payments", tags=["contractor-payments"])
WRITE_ROLES = ("company_admin", "staff")


@router.post("", response_model=ContractorPaymentOut, status_code=status.HTTP_201_CREATED)
def create_contractor_payment(
    body: ContractorPaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*WRITE_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    linked = (
        db.query(Contractor)
        .join(ContractorCompany, ContractorCompany.contractor_id == Contractor.id)
        .filter(Contractor.id == body.contractor_id,
                 ContractorCompany.company_id == current_user.company_id,
                 ContractorCompany.is_deleted.is_(False))
        .first()
    )
    if not linked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                             detail="Contractor not found for this company")

    if body.maintenance_request_id is not None:
        req = db.query(MaintenanceRequest).filter(
            MaintenanceRequest.id == body.maintenance_request_id
        ).first()
        if not req:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                                 detail="Maintenance request not found")

    payment = ContractorPayment(
        id=uuid.uuid4(),
        company_id=current_user.company_id,
        contractor_id=body.contractor_id,
        maintenance_request_id=body.maintenance_request_id,
        amount=body.amount,
        date_paid=body.date_paid,
        invoice_file=body.invoice_file,
        recorded_by=current_user.id,
    )
    db.add(payment)
    db.flush()

    write_audit_log(
        db,
        company_id=current_user.company_id,
        actor_id=current_user.id,
        actor_type=actor_type,
        action="create",
        entity_type="contractor_payment",
        entity_id=payment.id,
        after_state=body.model_dump(mode="json"),
    )

    result = ContractorPaymentOut.model_validate(payment)
    db.commit()
    return result


@router.get("", response_model=list[ContractorPaymentOut])
def list_contractor_payments(
    contractor_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_ROLES)),
):
    query = db.query(ContractorPayment)
    if contractor_id:
        query = query.filter(ContractorPayment.contractor_id == contractor_id)
    return query.order_by(ContractorPayment.date_paid.desc()).all()


@router.get("/{payment_id}", response_model=ContractorPaymentOut)
def get_contractor_payment(
    payment_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_ROLES)),
):
    payment = db.query(ContractorPayment).filter(ContractorPayment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contractor payment not found")
    return payment
