# Calling `maintenance_crud.py` (now an API client — migrated 2026-08)

**Absolute path** (same lesson from house-crud):
```
/opt/data/skills/maintenance-crud/scripts/maintenance_crud.py
```

Reuses the same environment variables as every other migrated skill.

## As a library
```python
from maintenance_crud import (
    insert_request, get_request, list_requests, update_request,
    verify_request, delete_request, restore_request,
    add_log_entry, list_log_entries, suggest_contractors_for_trade,
    MaintenanceCrudError,
)

request = insert_request(
    unit_reference="Claremont",
    problem_description="Toilet flooded, sink backed up",
    location_detail="hall bathroom",
    priority="high",
    reported_by_tenant_id="<tenant-id-from-tenant-crud>",
    tenant_availability="Home all week except Wednesday",
)

open_requests = list_requests(status="Submitted")
unit_requests = list_requests(unit_reference="Claremont")

request = get_request(request_id="...")

update_request(request_id="...", assigned_contractor_id="...", scheduled_date="2026-08-10")

update_request(request_id="...", status="Completed")

verify_request(request_id="...")

delete_request(request_id="...")
restore_request(request_id="...")

add_log_entry(request_id="...", entry_text="Tenant rescheduled from Thu to Fri")
entries = list_log_entries(request_id="...")

candidates = suggest_contractors_for_trade("plumbing")
```

**Removed** (raises `MaintenanceCrudError` if you try): `cost`,
`payment_method`, `completed_date`, `unit_label`, and updating
`reported_by_tenant_id` after creation.

## As a CLI
```bash
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py insert --unit-reference Claremont --problem-description "Toilet flooded" --location-detail "hall bathroom" --priority high
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py list --status Submitted
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py get --request-id <uuid>
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py update --request-id <uuid> --assigned-contractor-id <uuid> --scheduled-date 2026-08-10
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py update --request-id <uuid> --status Completed
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py verify --request-id <uuid>
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py delete --request-id <uuid>
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py restore --request-id <uuid>
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py log --request-id <uuid> --entry-text "Called plumber"
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py log-list --request-id <uuid>
python3 /opt/data/skills/maintenance-crud/scripts/maintenance_crud.py suggest-contractors --trade plumbing
```

`--modified-by` is gone from every subcommand.
