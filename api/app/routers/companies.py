from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import get_current_user, require_roles
from ..models import Company, User

router = APIRouter(prefix="/companies", tags=["companies"])


class CompanyOut(BaseModel):
    id: UUID
    name: str
    status: str
    contact_email: Optional[str] = None

    class Config:
        from_attributes = True


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
