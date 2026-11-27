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
    users = (
        db.query(User)
        .filter(User.is_deleted.is_(False))
        .order_by(User.role, User.username)
        .all()
    )
    if current_user.role == "company_admin":
        # Contractor logins belong to no company, so RLS hides them; a
        # company admin also manages the logins of contractors it created.
        with super_admin_session(db, company_id=current_user.company_id):
            users += (
                db.query(User)
                .join(Contractor, Contractor.user_id == User.id)
                .filter(Contractor.created_by_company_id == current_user.company_id,
                        User.is_deleted.is_(False))
                .all()
            )
            db.flush()
    return users


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


BELOW_COMPANY_ADMIN = ("staff", "tenant", "contractor")


def _editable(db: Session, user_id, me: User) -> User:
    """The login `me` may edit. Super admin: anyone. Company admin: only
    people below them in their own company (staff, tenants) and the
    logins of contractors their company created. Never other admins."""
    if me.role == "super_admin":
        user = db.query(User).filter(User.id == user_id, User.is_deleted.is_(False)).first()
        if user is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
    user = db.query(User).filter(User.id == user_id, User.is_deleted.is_(False)).first()
    if user is None:
        with super_admin_session(db, company_id=me.company_id):
            user = (
                db.query(User).join(Contractor, Contractor.user_id == User.id)
                .filter(User.id == user_id, User.is_deleted.is_(False),
                        Contractor.created_by_company_id == me.company_id)
                .first()
            )
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.role not in BELOW_COMPANY_ADMIN or user.id == me.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="You can only edit accounts below you: staff, tenants and your contractors.")
    return user


@router.patch("/{user_id}", response_model=UserOut)
def change_user(
    user_id: uuid.UUID,
    body: UserAdminUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "company_admin")),
    actor_type: str = Depends(get_actor_type),
):
    """Change a login's username, password or email.
      - super admin: any login
      - company admin: staff, tenants and their contractors (not other admins)
    A new password signs that person out everywhere (old tokens stop working)
    and unlinks their Telegram, so a leaked password is fully cut off."""
    is_sa = current_user.role == "super_admin"
    user = _editable(db, user_id, current_user)
    changes = body.model_dump(exclude_unset=True)
    new_username = clean_username(changes["username"]) if changes.get("username") is not None else None
    new_email = (changes.get("email") or None) if "email" in changes else ...
    if changes.get("password"):
        check_password(changes["password"])

    # Uniqueness is platform-wide, and a contractor's row has no company,
    # so the checks and writes run with the bypass on (company scope is
    # restored afterwards; the super admin already sees everything).
    def apply() -> dict:
        after = {}
        if new_username and new_username != user.username.lower():
            if db.query(User.id).filter(func.lower(User.username) == new_username, User.id != user.id).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is taken")
            user.username = after["username"] = new_username
        if new_email is not ... and (new_email or "").lower() != (user.email or "").lower():
            if new_email and db.query(User.id).filter(func.lower(User.email) == new_email.lower(), User.id != user.id).first():
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already used by another login")
            user.email = after["email"] = new_email
        if changes.get("password"):
            user.password_hash = hash_password(changes["password"])
            user.password_changed_at = datetime.now(timezone.utc)
            db.query(TelegramLink).filter(TelegramLink.user_id == user.id).delete()
            after["password"] = "changed"
        db.flush()
        return after

    before = {"username": user.username, "email": user.email}
    if is_sa:
        after = apply()
    else:
        with super_admin_session(db, company_id=current_user.company_id):
            after = apply()
    if not after:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Nothing to change.")
    write_audit_log(
        db, company_id=user.company_id or current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="update", entity_type="user", entity_id=user.id,
        before_state=before, after_state=after,
    )
    result = UserOut.model_validate(user)
    db.commit()
    return result


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_user(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("super_admin", "company_admin")),
    actor_type: str = Depends(get_actor_type),
):
    """Remove a login. The person's records (tenant, contractor) stay; only
    the ability to sign in goes away, and their tokens stop working at once.
      - super admin: anyone except themselves (including other admins)
      - company admin: only people below them: staff, tenants and the
        logins of contractors their company created. Not other admins.
    Same rules as editing (see _editable)."""
    if user_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="You can't remove your own account.")
    user = _editable(db, user_id, current_user)

    def apply():
        user.is_deleted = True
        db.query(Contractor).filter(Contractor.user_id == user.id).update({Contractor.user_id: None})
        db.query(Tenant).filter(Tenant.user_id == user.id).update({Tenant.user_id: None})
        db.query(TelegramLink).filter(TelegramLink.user_id == user.id).delete()
        db.flush()

    if current_user.role == "super_admin":
        apply()
    else:
        with super_admin_session(db, company_id=current_user.company_id):
            apply()
    write_audit_log(
        db, company_id=user.company_id or current_user.company_id, actor_id=current_user.id,
        actor_type=actor_type, action="soft_delete", entity_type="user", entity_id=user_id,
        before_state={"username": user.username, "role": user.role},
    )
    db.commit()
