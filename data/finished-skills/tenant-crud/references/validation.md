# Validation Rules — Tenants (via `tenant_crud.py`)

## Required on Insert
- `first_name` — required (becomes part of `name`; see `columns.md`).

That's it. `house_id`, `move_in_date`, `unit_label`, `lease_id`, and
`status` are NOT required anymore because they're not tenant fields at
all now — see `columns.md` for where each one actually lives (on the
lease, managed by rent-crud).

## What used to be required and no longer applies
- `house_id` used to require resolving an existing house before insert.
  **Not needed anymore** — a tenant can be created standalone, with no
  house/unit involved, and attached to one later via rent-crud.
- `move_in_date` used to be required. **Not needed anymore** — that's
  `lease.start_date`, set when rent-crud creates the lease.

## `status`
No longer a tenant field. See `columns.md` — the closest equivalent is
`lease.status` (active/ended) plus `lease.end_reason` for eviction
tracking specifically. If a user says "mark John as evicted," that's a
rent-crud operation on his lease, not a tenant-crud operation.

## Defaults
- `is_deleted`: false on insert.
- `email`, `phone`: null if not given — optional.
- `modified_by`: no longer applies (see `SKILL.md`).

## Delete-Time Check — now CLIENT-SIDE, not server-enforced
Before soft-deleting a tenant, `tenant_crud.py` itself checks (not the
API) whether the tenant has rent-payment history across any lease
they're attached to. If found and `force` isn't set, it returns a
warning instead of deleting — same shape/behavior as before, just
enforced in this script rather than by the server. Calling the API
directly, bypassing this script, skips that check entirely.
