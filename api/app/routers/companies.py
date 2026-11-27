"""
Companies are created only by super admin. There is no public signup:
POST /companies creates the company and its first company_admin login in
one transaction. That admin then adds staff, tenant and contractor logins
for their own company (see routers/users.py, tenants.py, contractors.py).
"""
import uuid
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db
from ..deps import get_actor_type, get_current_user, require_roles
from ..models import Company, User
from ..accounts import check_password, clean_username, ensure_free
from ..schemas import CompanyCreate
from ..security import hash_password

router = APIRouter(prefix="/companies", tags=["companies"])



class CompanyOut(BaseModel):
    id: UUID
    name: str
    status: str
    contact_email: Optional[str] = None

    class Config:
        from_attributes = True


@router.post("", response_model=CompanyOut, status_code=status.HTTP_201_CREATED)
def create_company(
    body: CompanyCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin")),
    actor_type: str = Depends(get_actor_type),
):
    """Super admin only: a new company plus its first company admin."""
    name = body.company_name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Company name is required")
    username = clean_username(body.admin_username)
    check_password(body.admin_password)
    ensure_free(db, username, body.admin_email, caller_is_super_admin=True)

    company = Company(id=uuid.uuid4(), name=name, contact_email=body.admin_email)
    db.add(company)
    db.flush()
    admin = User(id=uuid.uuid4(), company_id=company.id, role="company_admin", username=username,
                 email=body.admin_email, password_hash=hash_password(body.admin_password))
    db.add(admin)
    db.flush()

    write_audit_log(
        db, company_id=company.id, actor_id=current_user.id, actor_type=actor_type,
        action="create", entity_type="company", entity_id=company.id,
        after_state={"name": name, "admin_username": username},
    )
    result = CompanyOut.model_validate(company)
    db.commit()
    return result


@router.get("", response_model=list[CompanyOut])
def list_companies(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin")),
):
    """Every company on the platform — super admin only."""
    return db.query(Company).order_by(Company.name).all()


@router.get("/me", response_model=CompanyOut)
def my_company(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.company_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No company for this account")
    company = db.query(Company).filter(Company.id == current_user.company_id).first()
    if not company:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company
