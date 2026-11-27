# Calling `rent_crud.py` (now an API client — migrated 2026-08)

**Absolute path** (same lesson from house-crud):
```
/opt/data/skills/rent-crud/scripts/rent_crud.py
```

Reuses the same environment variables as house-crud/tenant-crud.

## As a library
```python
from rent_crud import (
    create_lease, get_lease, end_lease, update_lease,
    record_rent_change, get_rent_history, current_rent, get_rent_agreement,
    update_rent_agreement, delete_rent_agreement, restore_rent_agreement,
    insert_rent_payment, get_rent_payment, list_payments_for_lease,
    update_rent_payment, delete_rent_payment, restore_rent_payment,
    rent_status, arrears,
    resolve_lease_for_unit, resolve_lease_for_tenant_name,
    RentCrudError,
)

# NEW - no old-system equivalent. tenant-crud creates the person first,
# THIS creates the lease that actually houses them.
lease = create_lease(
    unit_reference="Claremont",
    tenant_ids=["<tenant-id-from-tenant-crud>"],
    start_date="2026-09-01",
    monthly_rent=2900.00,
    due_day_of_month=1,
    security_deposit_amount=2900.00,
)

lease = get_lease(lease_id="...")

# Ending a lease - this is where eviction tracking lives now
end_lease(lease_id="...", end_date="2026-11-15", end_reason="eviction")

# Genuine rent change - writes history AND updates the lease together
record_rent_change(lease_id="...", monthly_rent=3000, due_day_of_month=1, effective_date="2027-01-01")

history = get_rent_history(lease_id="...")
current = current_rent(lease_id="...")

update_rent_agreement(lease_id="...", history_id="...", monthly_rent=2950)

payment = insert_rent_payment(
    lease_id="...", amount_paid=1500.00, date_paid="2026-07-29",
    payment_method="other", late_fee=0, notes="Venmo - remainder expected next week",
)
payments = list_payments_for_lease(lease_id="...")
update_rent_payment(payment_id="...", amount_paid=1600.00)
delete_rent_payment(payment_id="...")
restore_rent_payment(payment_id="...")

# THIS MONTH only:
status = rent_status(lease_id="...")

# FULL multi-month picture - use this for "how much total," "last month too":
result = arrears(lease_id="...")

leases = resolve_lease_for_unit("Claremont")
leases = resolve_lease_for_unit("Claremont", active_only=False)
leases = resolve_lease_for_tenant_name("Dorsch")
```

## As a CLI
```bash
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py create-lease --unit-reference Claremont --tenant-id <uuid> --start-date 2026-09-01 --monthly-rent 2900 --due-day 1
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py get-lease --lease-id <uuid>
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py end-lease --lease-id <uuid> --end-date 2026-11-15 --end-reason eviction
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py record-rent-change --lease-id <uuid> --monthly-rent 3000 --due-day 1 --effective-date 2027-01-01
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py rent-history --lease-id <uuid>
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py insert-payment --lease-id <uuid> --amount-paid 1500 --date-paid 2026-07-29 --payment-method other
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py list-payments --lease-id <uuid>
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py rent-status --lease-id <uuid>
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py arrears --lease-id <uuid>
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py resolve-unit --unit-reference Claremont
python3 /opt/data/skills/rent-crud/scripts/rent_crud.py resolve-tenant --name Dorsch
```

**Changed:** all ids are now UUID strings, not integers. `--modified-by`
is gone from every subcommand — no longer applies (see `SKILL.md`).
