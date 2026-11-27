# Calling `pit_crew_crud.py` (now an API client — migrated 2026-08)

**Absolute path:**
```
/opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py
```

Reuses the same environment variables as every other migrated skill.

## As a library
```python
from pit_crew_crud import (
    insert_pit_crew, get_pit_crew, list_pit_crew,
    update_pit_crew, delete_pit_crew, restore_pit_crew,
    record_payment, list_payments,
    PitCrewCrudError,
)

crew_member = insert_pit_crew(
    first_name="Bob", last_name="Alvarez", primary_trade="plumber",
    preferred_payment_method="Venmo", phone="510-555-9876",
)

plumbers = list_pit_crew(primary_trade="plumber")
everyone = list_pit_crew()

crew_member = get_pit_crew(contractor_id="...")

update_pit_crew(contractor_id="...", phone="510-555-1111")

warning = delete_pit_crew(contractor_id="...")
if warning:
    print(f"Active on: {warning['active_requests']}")
    delete_pit_crew(contractor_id="...", force=True)

restore_pit_crew(contractor_id="...")

payment = record_payment(
    contractor_id="...", amount=180.00, date_paid="2026-08-10",
    maintenance_request_id="...",
)
history = list_payments(contractor_id="...")
```

## As a CLI
```bash
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py insert --first-name Bob --last-name Alvarez --primary-trade plumber --preferred-payment-method Venmo --phone 510-555-9876
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py list --primary-trade plumber
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py get --pit-crew-id <uuid>
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py update --pit-crew-id <uuid> --phone 510-555-1111
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py delete --pit-crew-id <uuid>
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py delete --pit-crew-id <uuid> --force
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py restore --pit-crew-id <uuid>
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py record-payment --contractor-id <uuid> --amount 180 --date-paid 2026-08-10 --maintenance-request-id <uuid>
python3 /opt/data/skills/pit-crew-crud/scripts/pit_crew_crud.py list-payments --contractor-id <uuid>
```

`--modified-by` is gone from every subcommand.
