"""
Who-can-see-which-accounts, enforced at two layers:
  - RLS (migration 008): a company session sees its own company's users
    plus its own row; company-less accounts (super_admin, contractor) are
    visible only to super admin.
  - This router: only admin/staff/super_admin may list accounts at all.
    Tenants (and contractors) only ever get /auth/me.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..deps import require_roles
from ..models import User
from ..schemas import UserOut
from ..scoping import STAFF_ROLES

router = APIRouter(prefix="/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*STAFF_ROLES)),
):
    return (
        db.query(User)
        .filter(User.is_deleted.is_(False))
        .order_by(User.role, User.email)
        .all()
    )
