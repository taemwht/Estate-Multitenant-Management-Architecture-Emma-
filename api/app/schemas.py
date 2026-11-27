from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr


class CompanyCreate(BaseModel):
    """Super admin creating a company and its first company admin."""
    company_name: str
    admin_username: str
    admin_password: str
    admin_email: Optional[EmailStr] = None


class LoginRequest(BaseModel):
    """Sign in with a username. `email` is still accepted (EMMA's skills
    sign in that way), and a username field holding an email works too."""
    username: Optional[str] = None
    email: Optional[str] = None
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: UUID
    company_id: Optional[UUID]
    role: str
    username: str
    email: Optional[str] = None

    class Config:
        from_attributes = True


class TenantCreate(BaseModel):
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None


class TenantLoginCreate(BaseModel):
    username: str
    password: str
    email: Optional[EmailStr] = None


class LoginCreate(BaseModel):
    """A login for an existing contractor record."""
    username: str
    password: str
    email: Optional[EmailStr] = None


class UserCreate(BaseModel):
    """Company admin adding a staff member or another admin."""
    username: str
    password: str
    email: Optional[EmailStr] = None
    role: str  # "staff" or "company_admin"


class JobOut(BaseModel):
    """What a contractor sees about a job assigned to them: the work and
    where it is, not the tenant's records or the company's books."""
    id: UUID
    company_name: str
    unit_reference: Optional[str] = None
    address: str
    description: str
    location_detail: Optional[str] = None
    tenant_availability: Optional[str] = None
    priority: str
    status: str
    scheduled_date: Optional[date] = None


class JobUpdate(BaseModel):
    status: str  # "In Progress", "On Hold" or "Completed"


class TenantOut(BaseModel):
    id: UUID
    company_id: UUID
    user_id: Optional[UUID]
    name: str
    email: Optional[str]
    phone: Optional[str]
    is_deleted: bool

    class Config:
        from_attributes = True


class DashboardSummaryOut(BaseModel):
    total_units: int
    occupied_units: int
    vacant_units: int
    active_leases: int
    total_monthly_rent: float
    rent_collected_this_month: float
    maintenance_by_status: dict
    annual_checkins_total: int
    annual_checkins_acknowledged: int
    annual_checkins_overdue: int
    security_deposits_held: float


class OverdueLeaseOut(BaseModel):
    lease_id: UUID
    rental_unit_id: UUID
    unit_reference: str
    monthly_rent: float
    due_day_of_month: int
    amount_paid_this_month: float
    tenant_names: list[str]


class ImportRowError(BaseModel):
    row_number: int
    unit_reference: Optional[str]
    error: str


class ImportResultOut(BaseModel):
    batch_id: UUID
    file_name: str
    rows_succeeded: int
    rows_failed: int
    errors: list[ImportRowError]


class ImportBatchOut(BaseModel):
    id: UUID
    company_id: UUID
    file_name: str
    status: str
    rows_succeeded: int
    rows_failed: int

    class Config:
        from_attributes = True


class AnnualCheckinCreate(BaseModel):
    lease_id: UUID
    year: int
    hazard_type: str  # co_detector, smoke_detector, mold, lead_paint, asbestos
    due_date: date


class AnnualCheckinAcknowledge(BaseModel):
    tenant_id: Optional[UUID] = None  # required if caller is admin/staff acting on a tenant's behalf
    evidence_file: Optional[str] = None


class AnnualCheckinOut(BaseModel):
    id: UUID
    company_id: UUID
    lease_id: UUID
    year: int
    hazard_type: str
    acknowledged_by: Optional[UUID]
    acknowledged_at: Optional[datetime]
    evidence_file: Optional[str]
    due_date: date
    reminder_count: int

    class Config:
        from_attributes = True


class ContractorCreate(BaseModel):
    name: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    trade: str  # now required, fixed vocabulary — see validation.md
    preferred_payment_method: Optional[str] = None
    notes: Optional[str] = None


class ContractorUpdate(BaseModel):
    name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    trade: Optional[str] = None
    preferred_payment_method: Optional[str] = None
    notes: Optional[str] = None


class ContractorOut(BaseModel):
    id: UUID
    name: str
    contact_email: Optional[str]
    contact_phone: Optional[str]
    trade: str
    preferred_payment_method: Optional[str]
    notes: Optional[str]
    is_deleted: bool
    has_login: bool = False

    class Config:
        from_attributes = True


class MaintenanceRequestCreate(BaseModel):
    rental_unit_id: UUID
    description: str
    priority: str = "normal"  # emergency / high / normal / low
    location_detail: Optional[str] = None
    tenant_availability: Optional[str] = None
    reported_by_tenant_id: Optional[UUID] = None
    photo_urls: list[str] = []  # stand-in until real file storage exists (S3 undecided in PRD)


class MaintenanceRequestUpdate(BaseModel):
    status: Optional[str] = None  # Submitted/Scheduled/In Progress/On Hold/Completed/Verified/Cancelled
    assigned_contractor_id: Optional[UUID] = None
    description: Optional[str] = None
    location_detail: Optional[str] = None
    tenant_availability: Optional[str] = None
    priority: Optional[str] = None
    scheduled_date: Optional[date] = None


class MaintenanceRequestOut(BaseModel):
    id: UUID
    company_id: UUID
    rental_unit_id: UUID
    submitted_by: Optional[UUID]
    reported_by_tenant_id: Optional[UUID]
    description: str
    location_detail: Optional[str]
    tenant_availability: Optional[str]
    priority: str
    status: str
    assigned_contractor_id: Optional[UUID]
    verified_by: Optional[UUID]
    scheduled_date: Optional[date]
    is_deleted: bool
    photo_urls: list[str] = []

    class Config:
        from_attributes = True


class MaintenanceLogCreate(BaseModel):
    entry_text: str


class MaintenanceLogOut(BaseModel):
    id: UUID
    maintenance_request_id: UUID
    entry_text: str
    recorded_by: Optional[UUID]

    class Config:
        from_attributes = True


class ContractorPaymentCreate(BaseModel):
    contractor_id: UUID
    maintenance_request_id: Optional[UUID] = None
    amount: float
    date_paid: date
    invoice_file: Optional[str] = None


class ContractorPaymentOut(BaseModel):
    id: UUID
    company_id: UUID
    contractor_id: UUID
    maintenance_request_id: Optional[UUID]
    amount: float
    date_paid: date
    invoice_file: Optional[str]
    recorded_by: Optional[UUID]

    class Config:
        from_attributes = True


class RentReceiptCreate(BaseModel):
    lease_id: UUID
    amount: float
    date_received: date
    method: str  # check, cash, zelle, venmo, bank_transfer, card, money_order, other
    method_detail: Optional[str] = None      # check number, or what "other" was
    paid_by_tenant_id: Optional[UUID] = None  # a tenant on this lease
    paid_by_name: Optional[str] = None        # someone else (subtenant, parent, agency)
    for_month: Optional[date] = None          # which month's rent (stored as the 1st)
    late_fee: float = 0
    notes: Optional[str] = None


class RentReceiptUpdate(BaseModel):
    # For correcting data-entry errors, not for logging a new payment.
    amount: Optional[float] = None
    date_received: Optional[date] = None
    method: Optional[str] = None
    method_detail: Optional[str] = None
    paid_by_tenant_id: Optional[UUID] = None
    paid_by_name: Optional[str] = None
    for_month: Optional[date] = None
    late_fee: Optional[float] = None
    notes: Optional[str] = None


class RentReceiptOut(BaseModel):
    id: UUID
    company_id: UUID
    lease_id: UUID
    amount: float
    date_received: date
    method: str
    method_detail: Optional[str] = None
    paid_by_tenant_id: Optional[UUID] = None
    paid_by_name: Optional[str] = None
    for_month: Optional[date] = None
    late_fee: float
    recorded_by: Optional[UUID]
    notes: Optional[str]
    is_deleted: bool

    class Config:
        from_attributes = True


class RentChangeCreate(BaseModel):
    """
    A genuine rent change over time (not a data-entry fix). Writes a new
    rent_rate_history row AND updates the lease's current monthly_rent/
    due_day_of_month to match — see leases.py for why both happen together.
    """
    monthly_rent: float
    due_day_of_month: int
    effective_date: date


class RentRateHistoryUpdate(BaseModel):
    monthly_rent: Optional[float] = None
    due_day_of_month: Optional[int] = None
    effective_date: Optional[date] = None


class RentRateHistoryOut(BaseModel):
    id: UUID
    lease_id: UUID
    monthly_rent: float
    due_day_of_month: int
    effective_date: date
    is_deleted: bool

    class Config:
        from_attributes = True


class MonthlyArrearsEntry(BaseModel):
    year: int
    month: int
    due_date: date
    expected_rent: float
    # Payments APPLIED to this month (oldest month first), not payments
    # received during it — a July payment made Aug 2 pays off July.
    paid: float
    outstanding: float


class ArrearsOut(BaseModel):
    lease_id: UUID
    total_owed: float
    total_paid: float
    # Money paid beyond everything charged so far (prepayment/overpayment).
    credit_balance: float
    monthly_breakdown: list[MonthlyArrearsEntry]


class RentStatusOut(BaseModel):
    lease_id: UUID
    monthly_rent: float
    due_day_of_month: int
    paid_this_period: float
    late_fee_charged_this_period: float
    outstanding: float
    is_overdue: bool


class SecurityDepositCreate(BaseModel):
    lease_id: UUID
    amount_collected: float = 0


class SecurityDepositUpdate(BaseModel):
    # Deliberately no way to touch amount_collected after creation —
    # only the move-out-time fields are editable, matching PRD 4.5
    # ("admin decides unilaterally, no in-system dispute flow").
    amount_returned: Optional[float] = None
    amount_deducted: Optional[float] = None
    deduction_reason: Optional[str] = None
    status: Optional[str] = None  # 'collected', 'held', 'returned', 'deducted'


class SecurityDepositOut(BaseModel):
    id: UUID
    company_id: UUID
    lease_id: UUID
    amount_collected: float
    amount_returned: Optional[float]
    amount_deducted: Optional[float]
    deduction_reason: Optional[str]
    status: str

    class Config:
        from_attributes = True


class LeaseCreate(BaseModel):
    rental_unit_id: UUID
    start_date: date
    end_date: Optional[date] = None
    monthly_rent: float
    due_day_of_month: int
    security_deposit_amount: float = 0
    tenant_ids: list[UUID]  # at least one co-tenant required to create a lease


class LeaseUpdate(BaseModel):
    end_date: Optional[date] = None
    monthly_rent: Optional[float] = None
    due_day_of_month: Optional[int] = None
    security_deposit_amount: Optional[float] = None
    status: Optional[str] = None  # 'active' or 'ended'
    end_reason: Optional[str] = None  # free text, e.g. "normal", "eviction" — see PRD note


class LeaseOut(BaseModel):
    id: UUID
    company_id: UUID
    rental_unit_id: UUID
    start_date: date
    end_date: Optional[date]
    monthly_rent: float
    due_day_of_month: int
    security_deposit_amount: float
    status: str
    end_reason: Optional[str]
    tenant_ids: list[UUID] = []

    class Config:
        from_attributes = True


class RentalUnitCreate(BaseModel):
    unit_reference: str
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    unit_type: Optional[str] = None
    year_built: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    notes: Optional[str] = None
    occupancy_status: Optional[str] = None


class RentalUnitUpdate(BaseModel):
    # All optional — PATCH semantics, only provided fields get changed.
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    unit_type: Optional[str] = None
    year_built: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[float] = None
    notes: Optional[str] = None
    occupancy_status: Optional[str] = None


class RentalUnitOut(BaseModel):
    id: UUID
    company_id: UUID
    unit_reference: str
    address_line1: Optional[str]
    address_line2: Optional[str]
    city: Optional[str]
    state: Optional[str]
    zip_code: Optional[str]
    unit_type: Optional[str]
    year_built: Optional[int]
    bedrooms: Optional[int]
    bathrooms: Optional[float]
    notes: Optional[str]
    occupancy_status: Optional[str]
    status: str
    is_deleted: bool

    class Config:
        from_attributes = True
