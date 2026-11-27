# Calling `tenant_crud.py` (now an API client — migrated 2026-08)

**Absolute path** (same lesson learned from house-crud — don't search for
this file, use the exact path):
```
/opt/data/skills/tenant-crud/scripts/tenant_crud.py
```

Calls the property-platform API instead of touching Postgres directly.
Reuses the SAME `API_BASE_URL`/`API_EMAIL`/`API_PASSWORD` environment
variables already configured for house-crud — nothing new to set up.

## As a library
```python
from tenant_crud import (
    insert_tenant, get_tenant, list_tenants, list_tenants_for_unit,
    list_tenants_by_lease, get_leases_for_tenant, update_tenant,
    delete_tenant, restore_tenant, TenantCrudError,
)

# Just creates the person — does NOT attach them to any unit/lease.
tenant = insert_tenant(
    first_name="Mia",
    last_name="Dorsch",
    phone="510-555-1234",
    email="mia@example.com",
)
# -> {"tenant_id": "...", "name": "Mia Dorsch", "email": "...",
#     "phone": "...", "house_id": None, "status": None, ...}

tenant = get_tenant(tenant_id="...")
tenants = list_tenants()                  # all non-deleted
tenants = list_tenants(name="Dorsch")     # search by name (partial match)

# "Who lives at Claremont right now" — chains unit -> active lease(s) -> tenants
rows = list_tenants_for_unit("Claremont")
# -> [{"lease_id": "...", "lease_status": "active", "start_date": "...",
#      "end_date": None, "end_reason": None, "tenant": {...}}]

# Full history at that unit, including past/ended leases:
rows = list_tenants_for_unit("Claremont", active_only=False)

tenants = list_tenants_by_lease(lease_id="...")   # co-tenants on one lease
leases = get_leases_for_tenant(tenant_id="...")   # which lease(s) is this person on

update_tenant(tenant_id="...", phone="510-555-9999")

# NOT valid anymore — these belong to the lease now, raises TenantCrudError:
# update_tenant(tenant_id="...", house_id=5)

result = delete_tenant(tenant_id="...")
if result and result.get("warning"):
    print(f"{result['payment_count']} payment(s) on record — force to proceed anyway")
    delete_tenant(tenant_id="...", force=True)

restore_tenant(tenant_id="...")
```

**To actually house a tenant** (attach them to a unit with a move-in
date and rent amount), create the tenant here, then use `rent-crud` to
create the lease with this tenant's id in `tenant_ids`. That hand-off is
described in `procedures/insert.md`.

## As a CLI
```bash
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py insert --first-name Mia --last-name Dorsch --phone 510-555-1234 --email mia@example.com
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py get --tenant-id <uuid>
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py list
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py list --name Dorsch
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py list-unit --unit-reference Claremont
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py list-unit --unit-reference Claremont --include-history
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py list-lease --lease-id <uuid>
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py update --tenant-id <uuid> --phone 510-555-9999
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py delete --tenant-id <uuid>
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py delete --tenant-id <uuid> --force
python3 /opt/data/skills/tenant-crud/scripts/tenant_crud.py restore --tenant-id <uuid>
```

**Changed:** `--tenant-id` is now a UUID string, not an integer. There's
no `--house-id`, `--move-in-date`, `--unit-label`, `--lease-id`, or
`--status` flag on `insert`/`update` anymore — passing old flags will
fail with an argparse error, not silently do nothing.

`--modified-by` still accepted everywhere for compatibility, does nothing.
