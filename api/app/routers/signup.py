"""
PRD 5.8 flagged this as needing "safeguards" without specifying which —
this builds the CORE mechanism (create company + first admin atomically,
under an RLS bypass since neither exists yet to scope a normal session
to) but does NOT add:
  - Rate limiting / anti-spam (anyone can create unlimited companies)
  - Email verification (admin_email is trusted as-is, no confirmation loop)
  - Payment/billing collection
  - CAPTCHA or similar abuse prevention
All of those need a real decision (which provider, what UX) before they
can be built — this endpoint is the foundation they'd sit on top of, not
a finished signup flow.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..database import get_db, super_admin_session
from ..models import Company, User
from ..schemas import SignupRequest, TokenResponse
from ..security import hash_password, create_access_token, create_refresh_token

router = APIRouter(prefix="/signup", tags=["signup"])

MIN_PASSWORD_LENGTH = 8  # minimal — not a real password policy, just guards against empty/trivial


@router.post("", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)):
    if len(body.admin_password) < MIN_PASSWORD_LENGTH:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Password must be at least {MIN_PASSWORD_LENGTH} characters",
        )

    # Both inserts happen inside ONE bypass block — neither the company
    # nor the admin user has a scoping company_id to check against yet,
    # so there's no point exiting the bypass between them (unlike
    # contractor creation, which resumes normal scoping right after for
    # an unrelated insert — nothing here needs that).
    with super_admin_session(db):
        existing = db.query(User).filter(User.email == body.admin_email).first()
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                                 detail="Email already registered")

        company = Company(id=uuid.uuid4(), name=body.company_name)
        db.add(company)
        db.flush()

        admin_user = User(
            id=uuid.uuid4(),
            company_id=company.id,
            role="company_admin",
            email=body.admin_email,
            password_hash=hash_password(body.admin_password),
        )
        db.add(admin_user)
        db.flush()

        company_id, user_id = company.id, admin_user.id

    db.commit()

    # Auto-login: return tokens immediately so the new admin doesn't have
    # to separately call /auth/login right after signing up.
    return TokenResponse(
        access_token=create_access_token(str(user_id), str(company_id), "company_admin"),
        refresh_token=create_refresh_token(str(user_id), str(company_id), "company_admin"),
    )
