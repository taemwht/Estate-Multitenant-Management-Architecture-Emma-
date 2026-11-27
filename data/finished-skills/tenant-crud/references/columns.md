# Tenant Fields — and where each old field went

| Old field | New home | Notes |
|---|---|---|
| `tenant_id` | `id` (UUID, was integer) | Changed type — not comparable to old saved values. |
| `first_name` + `last_name` | `name` (single field) | `tenant_crud.py` still accepts first/last name as separate arguments on insert/update and concatenates them — but reading a tenant back gives you one `name` string, not separated parts. |
| `phone` | `phone` | Unchanged. |
| `email` | `email` | Unchanged. |
| `house_id` | *(gone — see lease)* | Which unit a tenant lives in is now determined by which lease they're attached to (`lease.rental_unit_id`), not a field on the tenant. |
| `unit_label` | *(gone — see lease)* | The old free-text tag (e.g. "#A") distinguishing tenants within one house is replaced by having separate rental_unit + lease records per unit, not a label on the tenant. |
| `lease_id` (old lightweight grouping string) | `lease.id` (real entity) | A lease is now a full record (unit, dates, rent, due day) in its own right, not just a shared label. Managed by rent-crud. |
| `move_in_date` | `lease.start_date` | |
| `move_out_date` | `lease.end_date` | |
| `status` (active/past/evicted) | `lease.status` (active/ended) + `lease.end_reason` (free text) | `end_reason` was added specifically to preserve eviction tracking — write `"eviction"` there when that's why a lease ended. |
| `is_deleted` | `is_deleted` (boolean, was 0/1 integer) | Same meaning, different type. `tenant_crud.py` still returns 0/1 for compatibility. |
| `modified_by` | *(gone — audit log)* | The API's audit log now tracks who + Hermes-vs-web automatically. |
| `created_at` / `updated_at` | Same names | Unchanged. |

## Required-field behavior
Only `name` (derived from `first_name`, required) is required to create a
tenant now — `email` and `phone` are optional, same as before. Nothing
else is required at tenant-creation time anymore, since house/unit/dates
aren't tenant concerns.
