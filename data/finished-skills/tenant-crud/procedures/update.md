# Procedure: Update Tenant

**Confirmation required.** Show before/after values and wait for explicit
yes before writing.

## Steps
1. Resolve the target tenant (`procedures/lookup.md`).
2. Show a before/after summary of only the changing fields, e.g.:
   > Update Mia Dorsch: phone "510-555-1234" -> "510-555-9999". Confirm?
3. On explicit yes, call `update_tenant()`. Recorded automatically in the
   audit log — no `modified_by` to set yourself.
4. On anything other than a clear yes, do not write.

## Only `first_name`, `last_name`, `phone`, `email` are valid here
Anything else (house, unit, move-in/move-out date, status) belongs to
the lease now, not the tenant — see `columns.md`. Calling `update_tenant()`
with an old field name raises a clear error rather than silently doing
nothing, so you'll know immediately if you're trying to update something
that moved.

## Common case: "[Tenant] moved out [date]"
This is NOT a tenant-crud operation anymore — there's no `status` or
`move_out_date` on the tenant to change. This is a **rent-crud** update:
set `end_date` and `status: "ended"` (plus `end_reason` if eviction or
another specific reason applies) on the relevant **lease**. Resolve which
lease first (a tenant could theoretically be on more than one over time)
using `get_leases_for_tenant()`, then hand off to rent-crud's update
procedure for the actual write.
