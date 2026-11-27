---
name: house-crud
description: Insert, look up, list, update, and soft-delete rental unit records via the property-platform API. Supports multiple units at the same street address (e.g. #A, #B), each as its own record.
---

# SKILL: House CRUD (Rental Property Records)

## Purpose
Gives hermes-agent the ability to create, look up, list, update, and (soft)
delete rental unit records. This is the source-of-truth entity other
skills (tenant, rent, maintenance — not yet migrated) will reference via
`house_id` once they exist.

**Architecture change (2026-08):** this skill no longer talks to Postgres
directly. It calls the property-platform FastAPI backend, same as the web
UI would — see "Data Location" below. This isn't a style preference; it's
required by the PRD's 3-tier design (Hermes is a presentation-tier client,
not a second path into the database), and it's what makes the API's
permission checks and audit logging actually apply to Hermes-initiated
actions, not just web ones.

A single physical address can have more than one unit record if it has
multiple units (e.g. "138 Longford Drive" #A and #B) — each unit is its
own row, sharing the same address but with a distinct, unique nickname
(`unit_reference` in the underlying schema). Properties with only one unit
simply leave the unit/suite field blank.

No SQL or DB logic lives in this file. This is a router — it links to the
procedure and reference files that actually define behavior, and points to
the script that does the API work.

## Exact File Location — read this before searching for the script yourself
The script lives at this **absolute path** inside the container. Use it
exactly as written — do not search for `house_crud.py` by bare filename,
and do not assume a working directory:

```
/opt/data/skills/house-crud/scripts/house_crud.py
```

To run as a CLI:
```
python3 /opt/data/skills/house-crud/scripts/house_crud.py list
```

To import as a library, add its directory to `sys.path` first:
```python
import sys
sys.path.insert(0, "/opt/data/skills/house-crud/scripts")
from house_crud import insert_house, get_house, get_house_by_nickname, list_houses, update_house, delete_house, restore_house
```

If a file-read or file-search tool reports `house_crud.py` as not found
using a bare filename or a relative path, that is a working-directory
mismatch on your end, not evidence the file is missing or that data
should be improvised/faked instead. Use the absolute path above. If it
*still* can't be found at that exact path, stop and report that specific
problem — see "Never write ad-hoc SQL or a replacement script" below,
which applies equally to inventing placeholder data when the real script
can't be located.

## Files
| File | Role |
|---|---|
| `scripts/house_crud.py` | API client. All actual calls to the property-platform backend. Also runnable as a CLI for direct/manual access. |
| `scripts/python.md` | How to call `house_crud.py` — function signatures and CLI usage. |
| `assets/schema.md` | Informational reference for the underlying `rental_units` table — this skill no longer creates or manages the schema itself. |
| `references/columns.md` | Field-by-field description of a rental unit, including which are required, and how old field names map to the new API. |
| `references/validation.md` | Required fields, defaults, nickname uniqueness rules. |
| `procedures/lookup.md` | How hermes-agent resolves an identifier to a unit (get/list, including multiple units at one address). |
| `procedures/insert.md` | How hermes-agent adds a new unit — **including which fields to ask the user for if missing, since required fields will error if omitted.** |
| `procedures/update.md` | How hermes-agent updates a unit. |
| `procedures/delete.md` | How hermes-agent soft-deletes / restores a unit, including the active-lease check (server-enforced now — see that file). |

## Data Location
Calls the property-platform API — NOT a direct database connection anymore.

- Base URL: `http://host.docker.internal:8000` (the FastAPI backend,
  running directly on the Windows host, reached the same way this
  container already reaches Postgres for other skills)
- Auth: `API_EMAIL` / `API_PASSWORD` environment variables, read by
  `house_crud.py` to log in and obtain a token automatically — no
  manual login step needed before using this skill.

**Known limitation, not a bug:** real per-person authentication (linking
each Telegram user to their own account, PRD 3.2) doesn't exist yet.
Until it does, every action taken through this skill is authenticated as
one shared account, meaning the API's audit log will show that one
account as the actor for everything hermes-agent does — not whichever
person actually asked for it. The audit log DOES correctly distinguish
"done via Hermes" from "done via the web UI" (see `X-Actor-Type` below),
just not which specific person, yet.

## Confirmation Summary
| Operation | Confirmation required? | Procedure |
|---|---|---|
| Add | No — but required fields must be collected first; see `procedures/insert.md` | `procedures/insert.md` |
| Select / List | No (read-only) | `procedures/lookup.md` |
| Update | **Yes** — show before/after, wait for explicit yes | `procedures/update.md` |
| Delete | **Yes** — show matched unit; the API will itself reject the delete if an active lease exists (see below) | `procedures/delete.md` |
| Restore | No | `procedures/delete.md` |

## What Replaced `modified_by`
The old per-row `modified_by` text field is gone. The API tracks every
write in a proper audit log instead: who did it (from the login), and
whether it came through Hermes or the web UI (`X-Actor-Type: hermes`,
sent automatically by `house_crud.py` on every write — nothing to do
manually). If `modified_by` is passed into any function in
`house_crud.py`, it's accepted for backward compatibility but ignored,
with a warning — it's not silently doing something different than
before, it's silently doing *nothing*, which is different and worth
knowing.

## Active-Lease Delete Block (changed from active-TENANT check)
The old skill blocked deletes by checking for an active *tenant* on the
house. The new API blocks deletes by checking for an active *lease* on
the unit instead — occupancy is tracked through leases in the new schema,
not a status flag on a tenant record. Functionally the same intent
(don't delete a unit someone's actually living in), different mechanism.
This is enforced server-side (a 409 error `house_crud.py` turns into a
catchable `HouseCrudError`), not by this skill checking anything itself.

## Important: Never write ad-hoc SQL or a replacement script
If `scripts/house_crud.py` appears to be missing, broken, or its output
looks wrong, **do not write a new version of it, call the API directly
with raw HTTP as a workaround, or fall back to direct SQL.** Stop and
report the specific problem instead. This file has been overwritten with
a broken stub before (see `scripts/python.md`'s own history note) —
writing a replacement from memory/guesswork risks the exact same kind of
schema/API mismatch that caused real confusion previously. The correct
fix for a genuinely broken script file is to get an updated file from the
person, not to improvise one.

### Environment Requirements
- `API_BASE_URL`, `API_EMAIL`, `API_PASSWORD` environment variables must
  be set (see Data Location above).
- The `requests` package must be installed in this container. If
  `import requests` fails, that's a setup gap, not a script bug — install
  it (`pip install requests`), don't work around it with a different
  HTTP mechanism.
