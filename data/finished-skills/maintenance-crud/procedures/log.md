# Procedure: Append Maintenance Log Entry

No confirmation required.

## When to log vs. when to update a field
The log is for touchpoints, not facts that belong in a real column. If
what the user says implies a field change, make that update too — the
log entry alone is not a substitute.

- "Bob's running 30 minutes late" -> log entry only.
- "Tenant says Thursday doesn't work, let's do Friday instead" -> update
  `scheduled_date` (`procedures/update.md`) AND add a log entry noting
  the reschedule and why.
- "Tenant confirmed Bob can come by" -> log entry only.

## Steps
1. Resolve the target request.
2. Call `add_log_entry()` with `entry_text` capturing what happened in
   plain language.
3. Report back briefly, e.g. "Noted."
