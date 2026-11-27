# Procedure: Update House

**Confirmation required.** Show before/after values and wait for explicit
yes before writing.

## Steps
1. Resolve the target house (`procedures/lookup.md`). If the address has
   multiple units, make sure the right one is confirmed before proceeding.
2. If the update changes `nickname` — **not currently possible.**
   Renaming a unit's nickname isn't supported yet (a gap carried over
   from the 2026-08 migration, not a deliberate restriction). If asked to
   rename one, say so plainly rather than attempting it; don't try a
   delete-and-recreate workaround, since that would lose the unit's
   history and break anything referencing its id.
3. Show a before/after summary of only the fields changing, e.g.:
   > Update Longford A: status "vacant" -> "occupied". Confirm?
4. On explicit yes, call `update_house`. The update is recorded
   automatically in the platform's audit log (who made it, and that it
   came through Hermes) — there's no `modified_by` to set yourself
   anymore.
5. On anything other than a clear yes, do not write.
