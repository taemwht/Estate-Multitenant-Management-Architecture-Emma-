# Procedure: Delete (Soft) / Restore Pit Crew Member

**Confirmation required for delete.** Restore does not require
confirmation.

Delete only removes the contractor from THIS company's list. If other
companies also use the same contractor, they keep them.

## Delete Steps
1. Resolve the target pit crew member.
2. Call delete_pit_crew(contractor_id) — do not check for active
   assignments yourself first. The server does this automatically now.
3. If it returns a warning dict, relay it plainly, e.g.:
   > "Bob Alvarez is currently assigned to an in-progress request —
   > [description]. Deleting won't remove that request, but it will
   > mark Bob inactive and clear him from that assignment. Continue?"
   On explicit yes, call delete_pit_crew(contractor_id, force=True) —
   this both deletes AND automatically clears the assignment on any
   affected request in one step, no separate unassign call needed.
4. If it returns None with no warning, the contractor is already
   deleted — nothing further to confirm.

## Restore Steps
1. Resolve the target pit crew member among soft-deleted rows.
2. Call restore_pit_crew(contractor_id). No confirmation required.
