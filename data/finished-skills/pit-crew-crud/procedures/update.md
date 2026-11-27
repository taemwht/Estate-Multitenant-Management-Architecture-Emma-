# Procedure: Update Pit Crew Member

**Confirmation required.** Show before/after values and wait for
explicit yes before writing.

## Steps
1. Resolve the target pit crew member.
2. Show a before/after summary of only the changing fields, e.g.:
   > Update Bob Alvarez: phone "510-555-9876" -> "510-555-1111". Confirm?
3. On explicit yes, call update_pit_crew(). Recorded automatically in
   the audit log.
4. On anything other than a clear yes, do not write.

A contractor can be shared between companies. Only the company that
created the contractor can edit their details; for anyone else the API
returns 403. If that happens, tell the user the contractor's record is
managed by another company and nothing was changed.
