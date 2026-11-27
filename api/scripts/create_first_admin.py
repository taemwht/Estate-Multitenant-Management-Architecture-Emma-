"""
Creates one company + one company_admin user, so you have something
to log in with while /auth/signup doesn't exist yet (that's PRD 5.8 —
self-serve signup — one of the deferred open items).

Run from the project root:
    python scripts/create_first_admin.py
"""
import sys
import uuid
from getpass import getpass

sys.path.insert(0, ".")

from app.database import SessionLocal, set_rls_context  # noqa: E402
from app.models import Company, User  # noqa: E402
from app.security import hash_password  # noqa: E402


def main():
    company_name = input("Company name: ").strip()
    email = input("Admin email: ").strip()
    password = getpass("Admin password: ")

    db = SessionLocal()
    try:
        # Creating a company at all requires the super-admin bypass —
        # same reasoning as the login lookup in routers/auth.py.
        set_rls_context(db, company_id=None, is_super_admin=True)

        company = Company(id=uuid.uuid4(), name=company_name)
        db.add(company)
        db.flush()  # get company.id without committing yet

        # Now scope to the company we just made for the user insert —
        # WITH CHECK on `users` requires company_id = current_company_id().
        set_rls_context(db, company_id=str(company.id), is_super_admin=False)

        user = User(
            id=uuid.uuid4(),
            company_id=company.id,
            role="company_admin",
            email=email,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.commit()

        print(f"\nCreated company '{company.name}' ({company.id})")
        print(f"Created admin user '{user.email}' ({user.id})")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
