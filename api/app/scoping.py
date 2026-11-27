"""
Row scoping for the `tenant` role.

RLS isolates companies from each other, but inside one company every role
sees every row. That's right for admin/staff and wrong for tenants: a
tenant should only see their own tenant record, their own leases (and the
receipts, deposits, check-ins and rent figures hanging off them), the
units they currently rent, and the maintenance requests they reported.

Routers call tenant_scope_for() and, when it returns a scope (i.e. the
caller is a tenant), filter by it. Anything outside the scope 404s, the
same way another company's row does.
"""
import uuid
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import Lease, LeaseTenant, Tenant, User

# Roles that see everything in their company (super_admin sees everything).
STAFF_ROLES = ("super_admin", "company_admin", "staff")
# Staff plus tenants, for reads that tenants get a filtered view of.
STAFF_AND_TENANT_ROLES = STAFF_ROLES + ("tenant",)

# Who may do what inside a company:
#   staff         day-to-day work: units, tenants, leases, rent, deposits,
#                 maintenance, contractors, check-ins.
#   company_admin all of that, plus user accounts (staff, tenant and
#                 contractor logins), deleting/restoring records, and
#                 bulk import.
# Companies themselves (and each one's first admin) are created only by
# super_admin, via POST /companies.
ADMIN_ROLES = ("company_admin",)
# Reading account lists / import history: the company's admin, or super admin.
ACCOUNT_VIEW_ROLES = ("super_admin", "company_admin")


@dataclass
class TenantScope:
    tenant_id: Optional[uuid.UUID]
    lease_ids: set = field(default_factory=set)
    # Units on the tenant's ACTIVE leases. A past tenant shouldn't see the
    # unit (or file maintenance on it) once they've moved out.
    active_unit_ids: set = field(default_factory=set)


def tenant_scope_for(db: Session, user: User) -> Optional[TenantScope]:
    """None for non-tenant roles (no extra filtering). For a tenant, the
    rows they're allowed to see; empty if no tenant record is linked to
    their login yet."""
    if user.role != "tenant":
        return None

    tenant = (
        db.query(Tenant)
        .filter(Tenant.user_id == user.id, Tenant.is_deleted.is_(False))
        .first()
    )
    if not tenant:
        return TenantScope(tenant_id=None)

    lease_ids = {
        row.lease_id for row in
        db.query(LeaseTenant.lease_id).filter(LeaseTenant.tenant_id == tenant.id).all()
    }
    active_unit_ids = set()
    if lease_ids:
        active_unit_ids = {
            row.rental_unit_id for row in
            db.query(Lease.rental_unit_id)
            .filter(Lease.id.in_(lease_ids), Lease.status == "active")
            .all()
        }
    return TenantScope(tenant_id=tenant.id, lease_ids=lease_ids, active_unit_ids=active_unit_ids)


def ensure_lease_visible(scope: Optional[TenantScope], lease_id, detail: str = "Not found") -> None:
    """404 if the caller is a tenant and the lease isn't one of theirs."""
    if scope is not None and lease_id not in scope.lease_ids:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
