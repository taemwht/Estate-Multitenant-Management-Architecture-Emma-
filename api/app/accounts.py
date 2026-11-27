"""Shared rules for creating logins."""
import re
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import super_admin_session
from .models import User

USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,49}$")
MIN_PASSWORD_LENGTH = 8


def clean_username(raw: str) -> str:
    name = (raw or "").strip().lower()
    if not USERNAME_RE.match(name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username must be 3-50 characters: letters, numbers, dots, dashes or underscores.",
        )
    return name


def check_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters")


def ensure_free(db: Session, username: str, email: Optional[str], company_id=None,
                caller_is_super_admin: bool = False) -> None:
    """Usernames and emails are unique across the whole platform, so the
    check looks past RLS. It only reveals "taken or not". A super admin
    already sees every row; for anyone else the bypass is switched on just
    for these lookups and their own company scope is restored after."""
    if caller_is_super_admin:
        _check(db, username, email)
        return
    with super_admin_session(db, company_id=str(company_id) if company_id else None):
        _check(db, username, email)


def _check(db: Session, username: str, email: Optional[str]) -> None:
    if db.query(User.id).filter(func.lower(User.username) == username).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That username is taken")
    if email and db.query(User.id).filter(func.lower(User.email) == email.lower()).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That email is already used by another login")
