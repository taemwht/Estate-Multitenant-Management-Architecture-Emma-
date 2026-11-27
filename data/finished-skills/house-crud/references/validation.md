# Validation Rules — Rental Units (via `house_crud.py`)

## Required on Insert (ask if missing — do not attempt insert without these)
- `nickname` — required, and must be unique among non-deleted units
  *within your company* (case-insensitive, trimmed — same matching
  behavior as before). If a duplicate is proposed, reject and ask for a
  different nickname rather than inserting.
- `street_address` — required.
- `city` — required.
- `zip_code` — required.

See `procedures/insert.md` for exactly how/when to ask the user for
these. (Unchanged from before this migration.)

## Multiple units, one address
`street_address` is **not** unique — multiple unit records can share the
same address, each representing a different unit (distinguished by the
`unit` field and a unique `nickname`). This is intentional, not a data
error. Unchanged from before.

## Defaults
- `state`: defaults to `"CA"` if not specified.
- `unit`, `year_built`, `bedrooms`, `bathrooms`, `status`, `notes`: NULL if
  not specified — all genuinely optional.
- `is_deleted`: false on insert.
- `modified_by`: **no longer applies.** The API's audit log records the
  actor automatically (see `columns.md`). Any old logic that asked the
  user "who should this be attributed to" no longer needs to.

## Delete-Time Check — CHANGED, read this before assuming old behavior
The old skill checked the `tenants` table for an active tenant before
allowing a delete. **That check is gone** — replaced by a server-side
check for an **active lease** on the unit instead (the new schema tracks
occupancy through leases, not a tenant status field). Practically:

- You (hermes-agent) don't need to check anything yourself before
  calling `delete_house()` — the API enforces this and will reject the
  delete with a clear error if an active lease exists.
- `house_crud.py` turns that rejection into a `HouseCrudError` with the
  real reason in the message — catch it and relay the reason to the
  user, the same way you'd have relayed the old "active tenant" warning.
- The tenants API doesn't exist yet as of this migration, so in practice
  right now a lease is the only thing that can block a delete — but
  don't hard-code an assumption that leases are the *only* future
  reason a delete might be blocked; just relay whatever the API says.
