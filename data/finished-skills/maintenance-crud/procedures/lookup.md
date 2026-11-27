# Procedure: Lookup / List Maintenance Requests

Read-only. No confirmation required.

## Resolving a single request
Match on unit + rough description ("the flooded toilet at Claremont") or
by `id` if given directly. If multiple open requests plausibly match,
list them and ask which one.

## Listing requests
- "What's open right now?" -> `list_requests()` with no status filter —
  the API already excludes Cancelled/deleted by default, ordered by
  priority (emergency first) then submission time.
- "Show me everything at [unit]" -> `list_requests(unit_reference=...)`.
- "Show me [contractor]'s jobs" -> resolve the contractor
  (`pit-crew-crud`), `list_requests(assigned_contractor_id=...)`.
- "Show completed requests" / "what did we spend this year" ->
  `list_requests(status="Completed")`. For cost totals, that now means
  cross-referencing `pit-crew-crud`'s payment records by
  `maintenance_request_id` — cost doesn't live on the request anymore.
- "Show cancelled requests" -> `list_requests(status="Cancelled")`
  explicitly (hidden by default).
- Soft-deleted requests aren't retrievable through list at all currently
  — only `get_request()`/`restore_request()` by known id.

## Pulling the log alongside a request
When showing details for a single request, also pull `list_log_entries()`
so the full back-and-forth is visible, not just current field values.
