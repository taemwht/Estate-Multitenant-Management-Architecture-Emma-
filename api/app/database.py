from contextlib import contextmanager
from typing import Optional

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from .config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def get_db():
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def set_rls_context(db: Session, company_id: Optional[str], is_super_admin: bool = False,
                    user_id: Optional[str] = None) -> None:
    """
    Sets the two RLS session variables the schema's policies check
    (current_company_id() / is_super_admin() in schema.sql), scoped
    to the CURRENT TRANSACTION ONLY via SET LOCAL.

    Using SET LOCAL (not SET) matters here: with a connection pool,
    a plain SET would leak into whichever unrelated request happens
    to reuse this same pooled connection next. SET LOCAL resets
    automatically at transaction end, so there's no cross-request
    bleed no matter how the pool recycles connections.

    user_id (optional) sets app.current_user_id, which the users policy
    uses so a company-less user (contractor) can still see their own row.
    It's only written when given, so the super_admin_session() toggles
    below leave it alone for the rest of the transaction.
    """
    db.execute(text("SET LOCAL app.current_company_id = :cid"),
               {"cid": str(company_id) if company_id else ""})
    db.execute(text("SET LOCAL app.is_super_admin = :flag"),
               {"flag": "true" if is_super_admin else "false"})
    if user_id is not None:
        db.execute(text("SET LOCAL app.current_user_id = :uid"), {"uid": str(user_id)})


@contextmanager
def super_admin_session(db: Session, company_id: Optional[str] = None):
    """
    For the handful of operations that legitimately need to bypass
    company scoping before we know which company is involved yet —
    e.g. looking a user up by email during login (PRD 3.1), or creating
    a contractor (whose visibility comes from contractor_companies,
    which can't exist until the contractor row itself does).

    Restores `company_id` (not necessarily None) on exit — pass the
    calling user's own company_id if normal scoped queries need to
    resume within the SAME transaction right after this block (e.g.
    inserting a contractor_companies row immediately after the
    bypassed contractor insert). Omit it (defaults to None) for
    call sites like login where nothing else needs normal scoping
    afterward in that transaction.

    Use narrowly: only around the specific query that needs the
    bypass, never as a general-purpose escape hatch.
    """
    set_rls_context(db, company_id=company_id, is_super_admin=True)
    try:
        yield db
    finally:
        set_rls_context(db, company_id=company_id, is_super_admin=False)
