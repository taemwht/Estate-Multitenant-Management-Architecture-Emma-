"""
User accounts. Who can see and manage them:
  - super_admin   lists every account on the platform.
  - company_admin lists and manages its own company's accounts: adds staff
                  and other admins, removes accounts. (Tenant and
                  contractor logins are added from their own records:
                  POST /tenants/{id}/login, POST /contractors/{id}/login.)
  - staff, tenants, contractors: no account list at all, only /auth/me.

RLS (migration 008) backs this up: a company session can only ever see
its own company's users plus its own row.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..audit import write_audit_log
from ..database import get_db, super_admin_session
from ..deps import get_actor_type, require_roles
from datetime import datetime, timezone

from ..models import Contractor, TelegramLink, Tenant, User
from ..accounts import check_password, clean_username, ensure_free
from ..schemas import UserAdminUpdate, UserCreate, UserOut
from ..scoping import ACCOUNT_VIEW_ROLES, ADMIN_ROLES
from ..security import hash_password

router = APIRouter(prefix="/users", tags=["users"])

ADDABLE_ROLES = ("staff", "company_admin")


@router.get("", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ACCOUNT_VIEW_ROLES)),
):
    return (
        db.query(User)
        .filter(User.is_deleted.is_(False))
        .order_by(User.role, User.username)
        .all()
    )


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    body: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """Company admin adds a staff member (or another admin) to their own company."""
    if body.role not in ADDABLE_ROLES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"role must be one of {ADDABLE_ROLES}")
    username = clean_username(body.username)
    check_password(body.password)
    company_id = current_user.company_id
    ensure_free(db, username, body.email, company_id)
    user = User(id=uuid.uuid4(), company_id=company_id, role=body.role, username=username,
                email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    db.flush()
    write_audit_log(
        db, company_id=company_id, actor_id=current_user.id, actor_type=actor_type,
        action="create", entity_type="user", entity_id=user.id,
        after_state={"username": username, "role": body.role},
    )
    result = UserOut.model_validate(user)
    db.commit()
    return result


@router.patch("/{user_id}", response_model=UserOut)
def change_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin")),
    actor_type: str = Depends(get_actor_type),
):
    """Super admin changes any login's username, password or email.
    A new password signs that person out everywhere (their old tokens stop
    working) and unlinks their Telegram, so a leaked password is fully cut off."""
    user = db.query(User).filter(User.id == user_id, User.is_deleted.is_(False)).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    changes = body.model_dump(exclude_unset=True)
    before = {"username": user.username, "email": user.email}
    after = {}
    if changes.get("username") is not None:
        username = clean_username(changes["username"])
        if username != user.username.lower():
            ensure_free(db, username, None, caller_is_super_admin=True)
            user.username = after["username"] = username
    if "email" in changes:
        email = (changes["email"] or None)
        if email and (user.email or "").lower() != email.lower():
            taken = db.query(User.id).filter(func.lower(User.email) == email.lower(), User.id != user.id).first()
            if taken:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already used by another login")
        user.email = after["email"] = email
    if changes.get("password"):
        check_password(changes["password"])
        user.password_hash = hash_password(changes["password"])
        user.password_changed_at = datetime.now(timezone.utc)
        db.query(TelegramLink).filter(TelegramLink.user_id == user.id).delete()
        after["password"] = "changed"
    if not after:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to change.")
    db.flush()
    write_audit_log(
        db, company_id=user.company_id, actor_id=current_user.id, actor_type=actor_type,
        action="update", entity_type="user", entity_id=user.id,
        before_state=before, after_state=after,
    )
    result = UserOut.model_validate(user)
    db.commit()
    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(*ADMIN_ROLES)),
    actor_type: str = Depends(get_actor_type),
):
    """Company admin removes a login from their company. The person's records
    (tenant, contractor) stay; only the ability to sign in goes away.
    Their existing tokens stop working on the next request."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You can't remove your own account.")
    company_id = current_user.company_id
    user = db.query(User).filter(User.id == user_id, User.is_deleted.is_(False)).first()
    contractor = None
    if user is None:
        # A contractor login has no company, so RLS hides it from a company
        # session. The admin may remove it if the contractor is one their
        # company created.
        with super_admin_session(db, company_id=company_id):
            contractor = (
                db.query(Contractor)
                .filter(Contractor.user_id == user_id,
                        Contractor.created_by_company_id == company_id)
                .first()
            )
            if contractor is not None:
                user = db.query(User).filter(User.id == user_id, User.is_deleted.is_(False)).first()
    if user is None or (user.company_id != company_id and contractor is None):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    with super_admin_session(db, company_id=company_id):
        user.is_deleted = True
        if contractor is not None:
            contractor.user_id = None
        db.query(Tenant).filter(Tenant.user_id == user.id).update({Tenant.user_id: None})
        db.flush()
    write_audit_log(
        db, company_id=company_id, actor_id=current_user.id, actor_type=actor_type,
        action="soft_delete", entity_type="user", entity_id=user_id,
        before_state={"username": user.username, "role": user.role},
    )
    db.commit()
