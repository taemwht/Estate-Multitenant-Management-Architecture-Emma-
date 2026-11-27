# Procedure: Delete (Soft) / Restore Maintenance Request

**Confirmation required for delete.** Restore does not require
confirmation.

Note: soft-deleting a request is different from marking it `Cancelled`
(that's an Update — see `procedures/update.md`). Delete removes it from
default views entirely (logged in error, duplicate); `Cancelled` keeps
it visible in history as "reported but didn't proceed."

## Delete Steps
1. Resolve the target request.
2. Show the matched request and confirm, e.g.:
   > "Delete the flooded toilet request at Claremont (status: Submitted,
   > logged 2026-08-01)? This won't affect the associated log entries,
   > they'll just no longer show by default. Continue?"
3. On explicit yes, call `delete_request()`.

## Restore Steps
1. Resolve the target request among soft-deleted requests.
2. Call `restore_request()`. No confirmation required.

## Duplicate requests
If two open requests for the same unit look like the same issue (same
location + similar description), don't auto-delete either one — present
both and ask which to keep (default suggestion: keep the older one by
creation time, since it likely has more log history) before deleting the
other, per the standard delete confirmation flow above.

## Cross-skill note: contractor deletion
When a contractor is soft-deleted via `pit-crew-crud`, any maintenance
request still pointing at them via `assigned_contractor_id` should have
that field cleared — this is `pit-crew-crud`'s responsibility to handle
when that skill gets migrated, not something to implement here, but
worth knowing so it doesn't look like a bug if you see it.
