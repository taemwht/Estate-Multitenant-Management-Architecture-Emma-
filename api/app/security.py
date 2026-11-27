from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from passlib.context import CryptContext

from .config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def _create_token(subject: str, company_id: Optional[str], role: str,
                   token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "company_id": company_id,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_access_token(user_id: str, company_id: Optional[str], role: str) -> str:
    return _create_token(
        user_id, company_id, role, "access",
        timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(user_id: str, company_id: Optional[str], role: str) -> str:
    return _create_token(
        user_id, company_id, role, "refresh",
        timedelta(days=settings.refresh_token_expire_days),
    )


def issued_before_password_change(payload: dict, user) -> bool:
    """True if this token predates the user's last password change, i.e.
    it belongs to a session that should have ended (migration_014)."""
    changed = getattr(user, "password_changed_at", None)
    return bool(changed) and int(payload.get("iat", 0)) < int(changed.timestamp())


def decode_token(token: str) -> dict:
    """Raises jose.JWTError on invalid signature or expiry — callers catch it."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
