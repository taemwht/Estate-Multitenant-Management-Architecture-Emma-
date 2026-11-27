# Procedure: Delete (Soft) / Restore House

**Confirmation required for delete.** Restore does not require confirmation.

## Delete Steps
1. Resolve the target house. If the address has multiple units, confirm
   which specific unit/nickname is being deleted — deleting one unit at an
   address does not affect the others.
2. **CHANGED (2026-08):** do NOT check the `tenants` table yourself — that
   check no longer exists, and the tenants API doesn't exist yet anyway,
   so you have no way to run it even if you wanted to. Instead, the
   active-occupant check now happens server-side, based on active
   *leases* rather than tenant records:
   - Show the matched house and ask for confirmation as normal (step 3).
   - Attempt the delete (step 4).
   - If it's rejected, `delete_house` raises a `HouseCrudError` whose
     message explains why (e.g. an active lease exists) — relay that
     message to the user rather than proceeding or retrying silently.
     This replaces the old "warn before attempting" pattern with a
     "the server tells you if it's blocked, then you relay it" pattern —
     don't try to predict the block yourself.
3. Show the matched house and ask for confirmation as normal.
4. On explicit yes, call `delete_house`. This soft-deletes the row (the
   API sets a deleted flag and timestamp) — the row and all its data
   remain in the database, just excluded from default listings. Every
   delete is recorded automatically in the platform's audit log (who,
   and that it came through Hermes) — there's no `modified_by` to set
   yourself anymore.

## Restore Steps
1. Resolve the target house among soft-deleted houses.
2. Call `restore_house`. No confirmation required. Recorded in the audit
   log automatically, same as delete.
