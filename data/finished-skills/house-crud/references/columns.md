# Rental Unit Fields (via `house_crud.py`, API-backed)

This file describes the shape `house_crud.py` presents to callers — the
OLD field names, which the script translates to/from the new API
internally. You generally don't need to think about the new names unless
you're debugging the API directly (e.g. with psql or curl).

| Old field (what you use here) | New API field (underlying) | Type | Required | Notes |
|---|---|---|---|---|
| `house_id` | `id` | UUID string | auto | **Changed type** — used to be an integer, now a UUID string. Not comparable to old saved values. |
| `nickname` | `unit_reference` | text | **yes** | Must be unique among non-deleted units *within your company* (was globally unique before — not a practical difference for single-company use). Primary way to refer to a unit conversationally. |
| `street_address` | `address_line1` | text | **yes** | Multiple units can share the same street_address if they're different units at one property. |
| `unit` | `address_line2` | text | no | Nullable. Distinguishes units at a shared address (e.g. "#A", "#B"). Leave blank for single-unit properties. |
| `city` | `city` | text | **yes** | |
| `state` | `state` | text | no | Defaults to `"CA"` if not specified. |
| `zip_code` | `zip_code` | text | **yes** | |
| `year_built` | `year_built` | integer | no | Nullable. |
| `bedrooms` | `bedrooms` | integer | no | Nullable. |
| `bathrooms` | `bathrooms` | number | no | Nullable. |
| `status` | `occupancy_status` | text | no | Nullable, free text (e.g. "occupied", "vacant"). **Renamed on the API side** — the new schema's own `status` field means something different now (see below), so this old free-text meaning lives in `occupancy_status` instead. `house_crud.py` still calls it `status` in its own function signatures, so nothing changes in how you call it. |
| `notes` | `notes` | text | no | Nullable, freeform. |
| `is_deleted` | `is_deleted` | boolean (was int) | auto | Never set directly — only via delete/restore. `house_crud.py` still returns `0`/`1` for backward compatibility. |
| `modified_by` | *(removed)* | — | — | **No longer exists.** Replaced by the API's audit log (who + Hermes-vs-web, automatically). Passing this to `house_crud.py` is accepted but ignored, with a warning. |
| `created_at` | `created_at` | timestamp | auto | Set once on insert. |
| `updated_at` | `updated_at` | timestamp | auto | Refreshed on every write. |

## About the new API's own `status` field (not the same as the old `status`)
The underlying schema has a `status` column too, but it's reserved
strictly for `active`/`deleted` bookkeeping (soft-delete tracking) — it
is NOT the same thing as the old free-text occupancy status. If you're
ever looking at the database directly rather than going through
`house_crud.py`, don't confuse the two: `status` = deleted or not,
`occupancy_status` = vacant/occupied/whatever text was entered.

## Required-field behavior
`nickname`, `street_address`, `city`, and `zip_code` are still required —
same as before. `house_crud.py` (via the API) will reject a request
missing any of these; that's why `procedures/insert.md` requires
collecting all four (asking the user if needed) *before* attempting the
call, rather than letting it fail. This part is unchanged from the old
skill.
