from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy import text
from sqlalchemy.orm import Session

from .database import get_db, set_rls_context
from .models import User
from .security import decode_token, issued_before_password_change

bearer_scheme = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise unauthorized

    if payload.get("type") != "access":
        raise unauthorized

    user_id = payload.get("sub")
    company_id = payload.get("company_id")
    role = payload.get("role")
    if not user_id or not role:
        raise unauthorized

    # Set RLS context from the token's claims BEFORE querying — this is
    # what makes the lookup below itself RLS-scoped. It doubles as
    # revocation-on-delete: if the user row is gone or is_deleted, RLS
    # (or the filter) makes it invisible and we 401, even though the
    # JWT signature is still technically valid until it expires.
    set_rls_context(db, company_id=company_id, is_super_admin=(role == "super_admin"),
                    user_id=user_id)

    user = (
        db.query(User)
        .filter(User.id == user_id, User.is_deleted.is_(False))
        .first()
    )
    if not user or issued_before_password_change(payload, user):
        raise unauthorized

    return user


def require_roles(*allowed_roles: str):
    """
    Dependency factory for role-restricted endpoints, matching the
    Roles & Permissions table in the PRD (section 3). Usage:

        @router.post("/rental-units", dependencies=[Depends(require_roles("super_admin", "company_admin", "staff"))])

    Raises 403 (not 401 — the user IS authenticated, just not permitted)
    if their role isn't in the allowed set.
    """
    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted to perform this action",
            )
        return current_user

    return checker


def get_actor_type(x_actor_type: str = Header(default="user")) -> str:
    """
    PRD 6.3: every write must be audit-logged with actor_type of either
    'user' (direct web/API use) or 'hermes' (agent-initiated on a user's
    behalf). Defaults to 'user' — callers that ARE Hermes must explicitly
    send `X-Actor-Type: hermes` on every write request. Getting this
    wrong the other way (a Hermes call silently logged as 'user') would
    be the worse failure mode, so we don't try to guess.
    """
    normalized = x_actor_type.strip().lower()
    if normalized not in ("user", "hermes"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Actor-Type header must be 'user' or 'hermes' if provided",
        )
    return normalized
