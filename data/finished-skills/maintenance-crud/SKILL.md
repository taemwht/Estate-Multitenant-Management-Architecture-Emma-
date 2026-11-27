---
name: maintenance-crud
description: Insert, look up, list, update, and soft-delete maintenance request records — location, priority, contractor assignment, scheduling, and completion — plus a per-request follow-up log, via the property-platform API.
---

# SKILL: Maintenance CRUD (Repair Request Records)

## Purpose
Gives hermes-agent the ability to create, look up, list, update, and (soft)
delete maintenance request records, plus append timestamped follow-up log
entries as a request moves through its lifecycle.

**Architecture change (2026-08):** calls the property-platform FastAPI
backend, same as every other migrated skill — no direct database access.

This skill does NOT own contractor people records — that's `pit-crew-crud`
(not migrated yet as of this writing). `assigned_contractor_id` is a
soft reference, validated at write time, same loose-coupling philosophy
as before.

## Files
| File | Role |
|---|---|
| `scripts/maintenance_crud.py` | API client. Also runnable as a CLI. |
| `scripts/python.md` | Function signatures and CLI usage. |
| `assets/schema.md` | Informational reference for the underlying tables. |
| `references/columns.md` | Field-by-field description, old-to-new mapping. |
| `references/validation.md` | Required fields, defaults, status/priority values, the (fixed) status-transition rule. |
| `references/nlp-parsing.md` | Parsing a freeform tenant complaint and matching it to a contractor trade. |
| `procedures/lookup.md` | Resolving/listing requests. |
| `procedures/insert.md` | Logging a new request — including emergency handling. |
| `procedures/update.md` | Assignment, scheduling, status changes. |
| `procedures/complete.md` | The completion flow — now decoupled from payment recording. |
| `procedures/log.md` | Appending a follow-up entry. |
| `procedures/delete.md` | Soft-delete / restore. |

## Data Location
Same as every migrated skill: `http://host.docker.internal:8000`,
`API_EMAIL`/`API_PASSWORD` already configured, `X-Actor-Type: hermes`
sent automatically.

## Confirmation Summary
| Operation | Confirmation required? | Procedure |
|---|---|---|
| Add (new request) | No | `procedures/insert.md` |
| Select / List | No (read-only) | `procedures/lookup.md` |
| Update — assignment, scheduling, availability, priority, On Hold/Cancelled | **No** | `procedures/update.md` |
| Verify | No | (either tenant or staff, whichever confirms first) |
| Complete | **Yes** — the one write that always requires explicit confirmation | `procedures/complete.md` |
| Append log entry | No | `procedures/log.md` |
| Delete | **Yes** | `procedures/delete.md` |
| Restore | No | `procedures/delete.md` |

## Status Lifecycle — merged from both systems
`Submitted` (default at insert) -> `Scheduled` (auto, once BOTH
`assigned_contractor_id` AND a real `scheduled_date` are set together —
see the note below, this was a real bug in the first platform build) ->
`In Progress` -> `Completed` (confirmation required) -> `Verified`
(either the tenant or staff, whichever confirms first). `On Hold` from
`Submitted` or `Scheduled`; `Cancelled` from any non-terminal status.

**The auto-transition bug, fixed:** the very first version of this
platform's maintenance API advanced status based on the STATUS LABEL
being set to "Scheduled" directly — not on the actual old-system
condition (a contractor assigned AND a real work date, together). Fixed
server-side; this skill doesn't need to do anything differently, just
set both fields and the platform handles it correctly now.

## What Replaced `modified_by`
Gone, replaced by the audit log — same as every migrated skill.

## Cost and payment — now a separate, decoupled step
The old system required `cost` to mark something `completed`, storing it
directly on the request. The new platform splits this: `Completed` here
is purely "the physical work is done." Recording what it cost is a
SEPARATE action via `pit-crew-crud`'s contractor payment recording
(linked back to this request). See `procedures/complete.md`.

## Emergency reports — a real safety decision, not just data-modeling
For anything that reads as a genuine emergency (gas smell, no heat in
freezing conditions, etc.): mark `priority: emergency` and tell the
tenant plainly to contact 911 or their utility's emergency line
**themselves**. This skill/EMMA does NOT supply specific emergency phone
numbers or step-by-step safety instructions in the request — a wrong or
outdated number in an actual emergency is a real safety risk, not a data
quality issue. The maintenance request still gets logged with high
priority for follow-up, but it is not the mechanism for handling the
live emergency itself.

## Important: Never write ad-hoc SQL or a replacement script
Same rule as every migrated skill.

### Environment Requirements
Same as house-crud/tenant-crud/rent-crud — nothing new to set up.

### A note on this skill's own history
An earlier version of this file had accumulated session-specific
"learnings" (references to a specific past duplicate-request incident,
specific record IDs, first-person narration about what an agent decided
during one session) mixed into what's supposed to be stable policy. That
content has been retired — the genuinely reusable policy from it (soft-
delete by default, confirm before destructive actions, clear
`assigned_contractor_id` when a contractor is deleted) is folded into
`references/validation.md` and `procedures/delete.md` below. A skill
file accumulating an agent's own session narration over time, rather
than a human deciding what's permanent policy, is worth staying alert to
— not something to let happen quietly again.
