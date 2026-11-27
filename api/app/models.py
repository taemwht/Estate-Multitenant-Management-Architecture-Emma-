import uuid

from sqlalchemy import BigInteger, Column, String, Boolean, DateTime, Date, Numeric, Integer, SmallInteger, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from .database import Base

# NOTE: These map onto tables already created by db/schema.sql.
# Don't add table-creation logic here (no Base.metadata.create_all) —
# schema.sql is the single source of truth for DDL, including the RLS
# policies, which SQLAlchemy has no concept of. As each workflow gets
# built, add its model(s) here rather than reaching for autogeneration.


class Company(Base):
    __tablename__ = "companies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    status = Column(String(20), nullable=False, default="active")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    role = Column(String(20), nullable=False)
    username = Column(String(50), nullable=False)  # unique on lower(username), migration 009
    email = Column(String(255), nullable=True, unique=True)
    password_hash = Column(String(255), nullable=False)
    telegram_link_id = Column(String(255), unique=True, nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    company = relationship("Company")


class RentalUnit(Base):
    __tablename__ = "rental_units"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    unit_reference = Column(String(100), nullable=False)
    address_line1 = Column(String(255))
    address_line2 = Column(String(255))
    city = Column(String(100))
    state = Column(String(50))
    zip_code = Column(String(20))
    unit_type = Column(String(50))
    year_built = Column(Integer)
    bedrooms = Column(Integer)
    bathrooms = Column(Numeric(3, 1))
    notes = Column(Text)
    occupancy_status = Column(String(50))
    status = Column(String(20), nullable=False, default="active")
    is_deleted = Column(Boolean, nullable=False, default=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class Lease(Base):
    __tablename__ = "leases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    rental_unit_id = Column(UUID(as_uuid=True), ForeignKey("rental_units.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=True)
    monthly_rent = Column(Numeric(10, 2), nullable=False)
    due_day_of_month = Column(SmallInteger, nullable=False)
    security_deposit_amount = Column(Numeric(10, 2), nullable=False, default=0)
    status = Column(String(20), nullable=False, default="active")
    end_reason = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class RentReceipt(Base):
    __tablename__ = "rent_receipts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    date_received = Column(Date, nullable=False)
    method = Column(String(20), nullable=False)
    method_detail = Column(String(120))           # migration_011
    paid_by_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    paid_by_name = Column(String(120))
    for_month = Column(Date)
    late_fee = Column(Numeric(10, 2), nullable=False, default=0)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    notes = Column(Text)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class RentRateHistory(Base):
    __tablename__ = "rent_rate_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"), nullable=False)
    monthly_rent = Column(Numeric(10, 2), nullable=False)
    due_day_of_month = Column(SmallInteger, nullable=False)
    effective_date = Column(Date, nullable=False)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class SecurityDeposit(Base):
    __tablename__ = "security_deposits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"), nullable=False, unique=True)
    amount_collected = Column(Numeric(10, 2), nullable=False, default=0)
    amount_returned = Column(Numeric(10, 2))
    amount_deducted = Column(Numeric(10, 2))
    deduction_reason = Column(Text)
    status = Column(String(20), nullable=False, default="collected")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class Contractor(Base):
    __tablename__ = "contractors"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    contact_email = Column(String(255))
    contact_phone = Column(String(50))
    trade = Column(String(100), nullable=False)
    preferred_payment_method = Column(String(100))
    notes = Column(Text)
    # The company that created this contractor (migration 008). Only it
    # (or super admin) may edit the shared contractor record.
    created_by_company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    # Global delete, super admin only. A company "deleting" a contractor
    # sets ContractorCompany.is_deleted on its own link instead.
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class ContractorCompany(Base):
    __tablename__ = "contractor_companies"

    contractor_id = Column(UUID(as_uuid=True), ForeignKey("contractors.id"), primary_key=True)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    is_deleted = Column(Boolean, nullable=False, default=False)  # per-company soft delete
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MaintenanceRequest(Base):
    __tablename__ = "maintenance_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    rental_unit_id = Column(UUID(as_uuid=True), ForeignKey("rental_units.id"), nullable=False)
    submitted_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reported_by_tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    description = Column(Text, nullable=False)
    location_detail = Column(Text)
    tenant_availability = Column(Text)
    priority = Column(String(20), nullable=False, default="normal")
    status = Column(String(20), nullable=False, default="Submitted")
    assigned_contractor_id = Column(UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=True)
    verified_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    scheduled_date = Column(Date, nullable=True)  # the actual planned work date
    is_deleted = Column(Boolean, nullable=False, default=False)
    submitted_at = Column(DateTime(timezone=True), server_default=func.now())
    scheduled_at = Column(DateTime(timezone=True), nullable=True)  # timestamp of status change, not the work date
    in_progress_at = Column(DateTime(timezone=True), nullable=True)
    on_hold_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class MaintenanceLog(Base):
    __tablename__ = "maintenance_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    maintenance_request_id = Column(UUID(as_uuid=True), ForeignKey("maintenance_requests.id"), nullable=False)
    entry_text = Column(Text, nullable=False)
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MaintenancePhoto(Base):
    __tablename__ = "maintenance_photos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    maintenance_request_id = Column(UUID(as_uuid=True), ForeignKey("maintenance_requests.id"), nullable=False)
    file_url = Column(String(500), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())


class ContractorPayment(Base):
    __tablename__ = "contractor_payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    contractor_id = Column(UUID(as_uuid=True), ForeignKey("contractors.id"), nullable=False)
    maintenance_request_id = Column(UUID(as_uuid=True), ForeignKey("maintenance_requests.id"), nullable=True)
    amount = Column(Numeric(10, 2), nullable=False)
    date_paid = Column(Date, nullable=False)
    invoice_file = Column(String(500))
    recorded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    file_name = Column(String(255), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(20), nullable=False, default="processing")
    rows_succeeded = Column(Integer, nullable=False, default=0)
    rows_failed = Column(Integer, nullable=False, default=0)
    error_report_file = Column(String(500))


class AnnualCheckin(Base):
    __tablename__ = "annual_checkins"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"), nullable=False)
    year = Column(SmallInteger, nullable=False)
    hazard_type = Column(String(30), nullable=False)
    acknowledged_by = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=True)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    evidence_file = Column(String(500))
    due_date = Column(Date, nullable=False)
    reminder_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class LeaseTenant(Base):
    __tablename__ = "lease_tenants"

    lease_id = Column(UUID(as_uuid=True), ForeignKey("leases.id"), primary_key=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255))
    phone = Column(String(50))
    is_deleted = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_type = Column(String(10), nullable=False)  # 'user' or 'hermes'
    action = Column(String(100), nullable=False)
    entity_type = Column(String(100), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    before_state = Column(JSONB, nullable=True)
    after_state = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class TelegramLink(Base):
    """migration_010: which Telegram account belongs to which EMMA login."""
    __tablename__ = "telegram_links"

    telegram_user_id = Column(BigInteger, primary_key=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, unique=True)
    telegram_username = Column(String(64))
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Notification(Base):
    """migration_012: a message to one person (website bell + Telegram)."""
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    company_id = Column(UUID(as_uuid=True), ForeignKey("companies.id"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    kind = Column(String(30), nullable=False)
    title = Column(String(200), nullable=False)
    body = Column(Text)
    entity_type = Column(String(40))
    entity_id = Column(UUID(as_uuid=True))
    link_tab = Column(String(30))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    read_at = Column(DateTime(timezone=True))
    telegram_status = Column(String(20))
    followup_sent_at = Column(DateTime(timezone=True))
