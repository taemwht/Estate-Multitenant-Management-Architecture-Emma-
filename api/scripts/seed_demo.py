"""
Seeds the PUBLIC DEMO database with two companies and one login per role,
so every screen of the demo site has something to show. Refuses to run
twice. Passwords are generated and printed once.

    docker compose run --rm api python scripts/seed_demo.py

Never run this against the real property_platform database.
"""
import secrets
import sys
import uuid
from datetime import date, timedelta

sys.path.insert(0, ".")

from app.database import SessionLocal, set_rls_context  # noqa: E402
from app.models import (  # noqa: E402
    AnnualCheckin, Company, Contractor, ContractorCompany, Lease, LeaseTenant,
    MaintenanceRequest, RentRateHistory, RentReceipt, RentalUnit, Tenant, User,
)
from app.security import hash_password  # noqa: E402


def first_of_month(months_back: int) -> date:
    d = date.today().replace(day=1)
    for _ in range(months_back):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


def main():
    db = SessionLocal()
    accounts = []
    try:
        set_rls_context(db, company_id=None, is_super_admin=True)
        if db.query(User).filter(User.email == "superadmin@example.com").first():
            sys.exit("Demo data already seeded; nothing to do.")

        def user(role, company_id, email):
            pw = secrets.token_urlsafe(9)
            u = User(id=uuid.uuid4(), company_id=company_id, role=role,
                     email=email, password_hash=hash_password(pw))
            db.add(u)
            accounts.append((role, email, pw))
            return u

        user("super_admin", None, "superadmin@example.com")

        def company(name, slug, units):
            co = Company(id=uuid.uuid4(), name=name)
            db.add(co)
            db.flush()
            admin = user("company_admin", co.id, f"admin@{slug}.example.com")
            user("staff", co.id, f"staff@{slug}.example.com")
            db.flush()

            leases, requests = [], []
            for i, (ref, street, rent, tenant_name) in enumerate(units):
                unit = RentalUnit(id=uuid.uuid4(), company_id=co.id, unit_reference=ref,
                                  address_line1=street, city="Fremont", state="CA",
                                  bedrooms=2 + i % 2, bathrooms=1 + i % 2)
                tenant = Tenant(id=uuid.uuid4(), company_id=co.id, name=tenant_name,
                                email=f"{tenant_name.split()[0].lower()}@{slug}.example.com")
                db.add_all([unit, tenant])
                db.flush()
                tu = user("tenant", co.id, tenant.email)
                db.flush()
                tenant.user_id = tu.id

                start = first_of_month(3)
                lease = Lease(id=uuid.uuid4(), company_id=co.id, rental_unit_id=unit.id,
                              start_date=start, monthly_rent=rent, due_day_of_month=1,
                              security_deposit_amount=rent)
                db.add(lease)
                db.flush()
                db.add(LeaseTenant(lease_id=lease.id, tenant_id=tenant.id))
                db.add(RentRateHistory(id=uuid.uuid4(), company_id=co.id, lease_id=lease.id,
                                       monthly_rent=rent, due_day_of_month=1,
                                       effective_date=start, recorded_by=admin.id))
                # First tenant is fully paid; the others are a month or two behind.
                for m in range(3, i - 1 if i else -1, -1):
                    db.add(RentReceipt(id=uuid.uuid4(), company_id=co.id, lease_id=lease.id,
                                       amount=rent, date_received=first_of_month(m) + timedelta(days=2),
                                       method="check", recorded_by=admin.id))
                req = MaintenanceRequest(
                    id=uuid.uuid4(), company_id=co.id, rental_unit_id=unit.id,
                    submitted_by=tu.id, reported_by_tenant_id=tenant.id,
                    description=["Kitchen faucet drips", "Bedroom window won't latch",
                                 "Heater makes a clicking noise"][i % 3],
                    priority=["normal", "high", "low"][i % 3], status="Submitted")
                db.add(req)
                requests.append(req)
                db.add(AnnualCheckin(id=uuid.uuid4(), company_id=co.id, lease_id=lease.id,
                                     year=date.today().year, hazard_type="smoke_detector",
                                     due_date=date.today() + timedelta(days=14)))
                leases.append(lease)

            c = Contractor(id=uuid.uuid4(), name=f"{name.split()[0]} Plumbing",
                           trade="plumber", contact_phone="510-555-0100",
                           created_by_company_id=co.id)
            db.add(c)
            db.flush()
            db.add(ContractorCompany(contractor_id=c.id, company_id=co.id))
            db.flush()
            # The contractor gets a login and one scheduled job, so the
            # contractor view ("My jobs") has something to show.
            cu = user("contractor", None, f"plumber@{slug}.example.com")
            db.flush()
            c.user_id = cu.id
            job = requests[-1]
            job.assigned_contractor_id = c.id
            job.scheduled_date = date.today() + timedelta(days=3)
            job.status = "Scheduled"
            db.flush()

        company("Sunrise Properties", "sunrise", [
            ("SUN-101", "12 Maple St", 2400, "Alice Nguyen"),
            ("SUN-102", "14 Maple St", 2150, "Ben Carter"),
            ("SUN-201", "88 Oak Ave", 2800, "Chloe Diaz"),
        ])
        company("Harbor Rentals", "harbor", [
            ("HB-1", "5 Pier Rd", 1950, "Dev Patel"),
            ("HB-2", "7 Pier Rd", 2050, "Eva Rossi"),
        ])
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    print("Demo accounts (save these; passwords are not stored anywhere else):")
    for role, email, pw in accounts:
        print(f"  {role:<14} {email:<32} {pw}")


if __name__ == "__main__":
    main()
