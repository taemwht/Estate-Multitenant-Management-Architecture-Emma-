# Validation Rules — Contractors (via `pit_crew_crud.py`)

## Required on Insert
- `first_name` — required.
- `primary_trade` — required, must be one of the fixed set. If nothing
  reasonably matches, use 'other' and put the actual specialty in
  `notes` rather than inventing a new value or failing the insert.

## Trade Matching
Map conversational descriptions to the closest fixed value. Only fall
back to 'other' if genuinely nothing matches.

## Defaults
- `last_name`, `preferred_payment_method`, `phone`, `email`, `notes`:
  NULL if not specified.
- `is_deleted`: false on insert.
- `modified_by`: no longer applies.

## Delete-Time Check (now server-side, folded in from the retired
session-workflow file)
Before soft-deleting a contractor, the API itself checks for any
non-deleted maintenance request assigned to them with status in
Submitted/Scheduled/In Progress/On Hold. If found and force isn't set,
it returns a warning instead of deleting — you don't need to run this
check yourself. On an actual delete (no active assignments, or
force=True), the API also automatically clears assigned_contractor_id
on those requests — no separate unassign step needed first, unlike the
old manual workflow.
