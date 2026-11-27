---
name: tenant-crud
description: Insert, look up, list, update, and soft-delete tenant records (name, email, phone) via the property-platform API. Does NOT handle which unit a tenant lives in, move-in/move-out dates, or active/past/evicted status — those now live on the lease (rent-crud's territory).
---

# SKILL: Tenant CRUD (Tenant Records)

## Purpose
Gives hermes-agent the ability to create, look up, list, update, and (soft)
delete tenant records — people. **Architecture change (2026-08):** a
tenant is now a standalone person record (name, email, phone) with no
direct link to a house, unit, or lease at the tenant level. Everything
about WHERE a tenant lives and WHEN is a property of the LEASE they're
attached to, managed by `rent-crud`, not this skill.

If you're used to the old system: `house_id`, `unit_label`, `lease_id`,
`move_in_date`, `move_out_date`, and `status` (active/past/evicted) do
NOT exist on a tenant anymore. See `references/columns.md` for exactly
where each of those concepts moved to.

This skill also no longer talks to Postgres directly — it calls the
property-platform FastAPI backend, same as `house-crud`. See "Data
Location" below.

## Files
| File | Role |
|---|---|
| `scripts/tenant_crud.py` | API client. All actual calls to the property-platform backend. Also runnable as a CLI. |
| `scripts/python.md` | How to call `tenant_crud.py` — function signatures and CLI usage. |
| `assets/schema.md` | Informational reference for the underlying `tenants` table — this skill no longer creates or manages schema. |
| `references/columns.md` | Field-by-field description, including exactly which old fields moved to the lease. |
| `references/validation.md` | Required fields, defaults. |
| `references/nlp-parsing.md` | How to parse freeform tenant info (name/phone/email) into structured fields before insert. |
| `procedures/lookup.md` | How hermes-agent resolves a tenant, including "who lives at X" (now a multi-step lookup through leases). |
| `procedures/insert.md` | How hermes-agent adds a new tenant — note this ONLY creates the person record now; attaching them to a unit is a separate rent-crud step. |
| `procedures/update.md` | How hermes-agent updates a tenant. |
| `procedures/delete.md` | How hermes-agent soft-deletes / restores a tenant, including the rent-history warning (now enforced client-side, not by the server). |

## Data Location
Calls the property-platform API — NOT a direct database connection.
- Base URL: `http://host.docker.internal:8000` (same as house-crud)
- Auth: `API_EMAIL` / `API_PASSWORD` environment variables — already
  configured from the house-crud migration, nothing new to set up here.
- Same known limitation as house-crud: real per-person auth isn't built
  yet, so every action here is attributed to one shared account in the
  audit log, tagged `X-Actor-Type: hermes` to distinguish it from web-UI
  actions (just not which specific person asked for it).

## Confirmation Summary
| Operation | Confirmation required? | Procedure |
|---|---|---|
| Add | No — but freeform input must be parsed into structured fields first | `procedures/insert.md`, `references/nlp-parsing.md` |
| Select / List | No (read-only) | `procedures/lookup.md` |
| Update | **Yes** — show before/after, wait for explicit yes | `procedures/update.md` |
| Delete | **Yes** — show matched tenant; warn if rent history exists (client-side check, see delete.md) | `procedures/delete.md` |
| Restore | No | `procedures/delete.md` |

## What Replaced `modified_by`
Same as house-crud: gone, replaced by the API's audit log (who + Hermes-
vs-web, automatic). Passing `modified_by` into `tenant_crud.py` is
accepted for compatibility but ignored, with a warning.

## Relationship Notes — READ THIS, the model changed shape
- A tenant is now just a person. Creating one here does **not** attach
  them to any unit, lease, or move-in date.
- To actually house a tenant, `rent-crud` creates a **lease** (rich
  entity: unit, dates, rent amount, due day) and attaches one or more
  existing tenant IDs to it. **Create the tenant here first, then use
  rent-crud to build the lease with this tenant's id.**
- "Who lives at [house]" is no longer a direct tenant query — it's
  resolved by finding the unit, then its active lease(s), then the
  tenants attached to that lease. `list_tenants_for_unit()` in
  `tenant_crud.py` does this chain for you; see `procedures/lookup.md`.
- Eviction tracking, which mattered enough to build deliberately: lives
  on the lease now (`lease.status = 'ended'` + `lease.end_reason`, free
  text, e.g. `"eviction"`) — not as a tenant status value.

## Important: Never write ad-hoc SQL or a replacement script
Same rule as house-crud: if `scripts/tenant_crud.py` looks broken or
missing, stop and report it — don't improvise a replacement or fall back
to direct SQL/HTTP.

### Environment Requirements
`API_BASE_URL`, `API_EMAIL`, `API_PASSWORD`, and the `requests` package
are all already set up from the house-crud migration — nothing new
needed for this skill specifically.
