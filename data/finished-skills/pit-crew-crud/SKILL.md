---
name: pit-crew-crud
description: Insert, look up, list, update, and soft-delete pit crew (contractor) records — the people who fix maintenance issues across all units — plus recording what they were paid, via the property-platform API.
---

# SKILL: Pit Crew CRUD (Contractor Records)

## Purpose
Gives hermes-agent the ability to create, look up, list, update, and (soft)
delete contractor records, plus record payments to them. A contractor is
NOT tied to any one unit — the same plumber works across your whole
portfolio.

**Architecture change (2026-08):** calls the property-platform FastAPI
backend, same as every other migrated skill.

## Files
| File | Role |
|---|---|
| `scripts/pit_crew_crud.py` | API client. Also runnable as a CLI. |
| `scripts/python.md` | Function signatures and CLI usage. |
| `assets/schema.md` | Informational reference for the `contractors` table. |
| `references/columns.md` | Field-by-field description, old-to-new mapping. |
| `references/validation.md` | Required fields, the (now server-enforced again) `trade` vocabulary, delete-time check. |
| `procedures/lookup.md` | Resolving/listing contractors, trade matching. |
| `procedures/insert.md` | Adding a new contractor. |
| `procedures/update.md` | Updating a contractor. |
| `procedures/delete.md` | Soft-delete / restore, including the active-assignment warning. |

## Data Location
Same as every migrated skill: `http://host.docker.internal:8000`,
`API_EMAIL`/`API_PASSWORD` already configured, `X-Actor-Type: hermes`
sent automatically.

## Confirmation Summary
| Operation | Confirmation required? | Procedure |
|---|---|---|
| Add | No | `procedures/insert.md` |
| Select / List | No (read-only) | `procedures/lookup.md` |
| Update | **Yes** — show before/after | `procedures/update.md` |
| Delete | **Yes** — warns if actively assigned to an open maintenance request | `procedures/delete.md` |
| Restore | No | `procedures/delete.md` |
| Record a payment | Not gated by this skill directly — see `maintenance-crud`'s `procedures/complete.md` for how the two skills hand off | — |

## What Replaced `modified_by`
Gone, replaced by the audit log — same as every migrated skill.

## A real bug found and fixed migrating this skill
`maintenance-crud`'s trade-matching doc had mapped plumbing problems to
`trade="plumbing"` — but this skill's actual fixed vocabulary (only
visible once these files were seen) uses `"plumber"`. Those never
matched; a plumbing complaint would have silently found zero candidates.
Fixed in both places, and the database now enforces the fixed vocabulary
again (it had quietly become unconstrained free text during the
platform's initial build) so a mismatch like this can't happen silently
again.

## Delete warning check — now server-side, and auto-cleans up
The active-assignment check before deleting a contractor used to require
a separate manual unassign step first (per the old system's session
workflow). It's now server-side and automatic: attempting to delete
someone with active assignments returns a warning listing those
requests; deleting with force=True (after the user confirms) also
automatically clears assigned_contractor_id on those requests — no
manual unassign step needed.

## Contractor payments — genuinely new here
Cost used to live directly on maintenance_requests in the old system.
It's a separate entity now (record_payment()), linked back to a
maintenance request by id. See maintenance-crud's
procedures/complete.md for the two-skill handoff.

## Important: Never write ad-hoc SQL or a replacement script
Same rule as every migrated skill.

### A note on this skill's own history
An earlier file, pit-crew-deletion-workflow.md, was a session-transcript-
style document (specific past record IDs, first-person narration of one
session's decisions) — the same pattern already found and retired in
maintenance-crud. Retired here too; the genuinely reusable policy
(unassign-then-delete, warn with active-request details) is folded into
references/validation.md and procedures/delete.md below.

### Environment Requirements
Same as every migrated skill — nothing new to set up.
