# Validation Rules — Maintenance Requests / Log

## Required on Insert
- `unit_reference` — must resolve to an existing rental unit.
- `problem_description` (-> `description`) — required, raw text. Don't
  paraphrase away detail the tenant gave you.

## Status Lifecycle & Transition Rule (fixed from the first platform build)
- `status` defaults to `Submitted`.
- Moves to `Scheduled` automatically once BOTH `assigned_contractor_id`
  AND a real `scheduled_date` are set (in the same call, or one already
  present and the other newly set). This is enforced server-side now —
  you don't need to check or set status yourself when assigning +
  scheduling.
- `In Progress`, `On Hold` (from Submitted or Scheduled), `Cancelled`
  (from any non-terminal status) are set explicitly via update.
- `Completed` **always requires explicit confirmation** — see
  `procedures/complete.md`. Unlike the old system, `cost` is NOT
  required to complete — cost/payment now live in `pit-crew-crud`
  entirely, decoupled from this status.
- `Verified` — either tenant or staff, via the dedicated verify action,
  not a plain status update.

## Defaults
- `priority`: `normal` if not specified — infer `emergency` only when
  the description clearly indicates one (no heat/water/gas leak/security
  issue); don't guess emergency casually, and don't downgrade something
  the tenant explicitly flagged as urgent.
- `status`: `Submitted` on insert.
- Everything else optional: NULL if not specified.
- `is_deleted`: false on insert.
- `modified_by`: no longer applies.

## Assigning a Contractor
Resolve via `suggest_contractors_for_trade()` if the user wants a
suggestion rather than naming someone — never assign without the user
confirming who, even though the assignment write itself needs no
separate confirmation step.

## Destructive-action policy (folded in from retired session notes)
- Soft-delete is the default for any deletion — a hard delete is never
  performed by this skill.
- Any destructive or state-changing action should be shown to the user
  as a clear before-state, with explicit confirmation, before writing.
- If a contractor is soft-deleted (via `pit-crew-crud`), any maintenance
  request still referencing them via `assigned_contractor_id` should
  have that field cleared to keep data consistent — this needs to be
  built into `pit-crew-crud`'s delete flow when that skill is migrated;
  noting the requirement here since it's this table that's affected.

## `maintenance_log` Entries
- `request_id` must resolve to an existing, non-deleted request.
- `entry_text` required.
- Purely a timestamped note — no field changes happen through the log.
  If an entry implies a real change (new `scheduled_date`, a status
  change), make that update too, don't let it live only in the log.
