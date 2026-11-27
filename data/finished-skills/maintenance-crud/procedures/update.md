# Procedure: Update Maintenance Request

**No confirmation required** for updates in this procedure — the ONE
update that does require confirmation (marking `Completed`) is handled
separately in `procedures/complete.md`, not here.

## Steps
1. Resolve the target request.
2. Apply the change(s) directly — no before/after confirmation needed for:
   - Assigning/reassigning `assigned_contractor_id`
   - Setting/changing `scheduled_date`
   - Updating `tenant_availability`, `location_detail`, `description`
   - Changing `priority`
   - Changing `status` to `On Hold` or `Cancelled`
3. **Auto-transition is handled server-side now** — if you set both
   `assigned_contractor_id` and `scheduled_date`, the platform advances
   status to `Scheduled` on its own. You don't need to also set status
   yourself in that call.
4. Report back what changed in plain language.

## Assigning a contractor without a name in hand
If the user asks "who should I call," use
`suggest_contractors_for_trade()` and present candidates — don't assign
until the user picks one, even though the write itself needs no separate
confirmation.

## Marking completed
Do NOT handle a `Completed` status change here — route to
`procedures/complete.md`, which requires confirmation.

## Verifying
Verification is its own action (`verify_request()`), not a status update
through this procedure — see `SKILL.md`'s confirmation table.
