---
name: rent-crud
description: Create and manage leases (unit + tenants + rent + dates), track rent-rate changes over time, log rent payments, and answer "who owes what" — both a quick this-month check and a full multi-month arrears total — via the property-platform API.
---

# SKILL: Rent CRUD (Leases, Rent History, Payments)

## Purpose — architecture changed more here than in house-crud or tenant-crud
The old system had no first-class "lease" — a `lease_id` was just a text
label generated when a tenant was inserted. **In the new system, creating
a lease is THIS skill's job**, not tenant-crud's. The flow is now:
1. `tenant-crud` creates the person (name, email, phone) — nothing lease-
   related.
2. **`rent-crud` creates the lease** — unit, dates, rent, due day,
   attaching the tenant(s) created in step 1. This is `create_lease()`,
   and it has no old-system equivalent because the old system never had
   a distinct lease-creation step.

No SQL or DB logic lives in this file — it calls the property-platform
FastAPI backend, same as house-crud and tenant-crud.

## Files
| File | Role |
|---|---|
| `scripts/rent_crud.py` | API client for lease lifecycle, rent-rate history, and payments. Also runnable as a CLI. |
| `scripts/python.md` | How to call `rent_crud.py` — function signatures and CLI usage. |
| `assets/schema.md` | Informational reference for the underlying tables. |
| `references/columns.md` | Field-by-field description, old-to-new mapping. |
| `references/validation.md` | Required fields, defaults. |
| `references/nlp-parsing.md` | How to parse conversational payment amounts ("fifteen hundred") into numeric fields. |
| `procedures/lookup.md` | How hermes-agent answers "who owes what" — both the quick and full-history versions — and resolves leases by unit/tenant. |
| `procedures/insert.md` | How hermes-agent creates a lease, records a rent change, or logs a payment (all three require confirmation). |
| `procedures/update.md` | How hermes-agent corrects a data-entry error (distinct from recording an actual rent change). |
| `procedures/delete.md` | How hermes-agent soft-deletes / restores lease/history/payment records. |

## Data Location
Same as house-crud/tenant-crud: `http://host.docker.internal:8000`,
`API_EMAIL`/`API_PASSWORD` already configured, `X-Actor-Type: hermes`
sent automatically on writes.

## Confirmation Summary
| Operation | Confirmation required? | Procedure |
|---|---|---|
| Create lease | **Yes** — show unit, tenants, dates, rent, due day before saving | `procedures/insert.md` |
| Record rent change | **Yes** — show parsed amount/due day/effective date | `procedures/insert.md` |
| Log a payment | **Yes** — show parsed amount/date/method/late fee | `procedures/insert.md` |
| Select / List / "who owes what" | No (read-only) | `procedures/lookup.md` |
| Update (data-entry correction) | **Yes** — show before/after | `procedures/update.md` |
| End a lease | **Yes** — show end date and reason if given | `procedures/update.md` |
| Delete | **Yes** | `procedures/delete.md` |
| Restore | No | `procedures/delete.md` |

Same as before: this is the one skill where Add always requires
confirmation, even more so now that it also covers creating leases
(money + tenancy commitments, not just a rate/payment record).

## What Replaced `modified_by`
Gone, replaced by the API's audit log — same as the other two skills.

## "Who owes what" — now TWO separate questions, not one
The old system had a single `amount_owed_for_lease()`. The new system
splits this into two functions because they answer genuinely different
questions:
- **`rent_status(lease_id)`** — THIS MONTH only. Quick snapshot.
- **`arrears(lease_id)`** — full history, `total_owed` across every
  month since the lease started, with a month-by-month breakdown, each
  month correctly priced at whatever rate applied THEN (not just the
  current rate). Built specifically to support tracking someone who's
  fallen behind and is catching up gradually — not just a binary
  "overdue this month" flag. Use this one whenever the question is about
  more than the current month.

## Eviction tracking
Lives on the lease now: `end_lease(lease_id, end_date, end_reason="eviction")`.
Not a tenant field anymore — see tenant-crud's migration notes.

## Important: Never write ad-hoc SQL or a replacement script
Same rule as the other two skills.

### Environment Requirements
Same as house-crud/tenant-crud — nothing new to set up.
