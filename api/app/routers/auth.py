from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from jose import JWTError
from sqlalchemy.orm import Session

from ..database import get_db, super_admin_session
from ..deps import get_current_user
from ..models import User
from ..schemas import LoginRequest, RefreshRequest, TokenResponse, AccessTokenResponse, UserOut
from ..security import verify_password, create_access_token, create_refresh_token, decode_token, issued_before_password_change

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    # We don't know the user's company yet — that's the whole point of
    # this lookup — so it has to run with the bypass. Scoped narrowly
    # to this one query, and email is globally unique, so this isn't
    # exposing anything cross-company beyond "does this email exist."
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect username or password",
    )
    ident = (body.username or body.email or "").strip().lower()
    if not ident:
        raise invalid
    column = User.email if "@" in ident else User.username
    with super_admin_session(db):
        user = (
            db.query(User)
            .filter(func.lower(column) == ident, User.is_deleted.is_(False))
            .first()
        )

    if not user or not verify_password(body.password, user.password_hash):
        raise invalid

    company_id = str(user.company_id) if user.company_id else None
    return TokenResponse(
        access_token=create_access_token(str(user.id), company_id, user.role),
        refresh_token=create_refresh_token(str(user.id), company_id, user.role),
    )


@router.post("/refresh", response_model=AccessTokenResponse)
def refresh(body: RefreshRequest, db: Session = Depends(get_db)):
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired refresh token",
    )
    try:
        payload = decode_token(body.refresh_token)
    except JWTError:
        raise unauthorized

    if payload.get("type") != "refresh":
        raise unauthorized

    # Re-read the user instead of trusting the refresh token's claims:
    # a deleted user gets a 401, and a changed role/company takes effect
    # on the next refresh instead of living on for the token's 7 days.
    # Still deferred: revoking one specific refresh token (logout, leak)
    # needs DB-backed tokens.
    user_id = payload.get("sub")
    if not user_id:
        raise unauthorized
    with super_admin_session(db):
        user = (
            db.query(User)
            .filter(User.id == user_id, User.is_deleted.is_(False))
            .first()
        )
    if not user or issued_before_password_change(payload, user):
        raise unauthorized

    company_id = str(user.company_id) if user.company_id else None
    return AccessTokenResponse(
        access_token=create_access_token(str(user.id), company_id, user.role)
    )


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)):
    return current_user
