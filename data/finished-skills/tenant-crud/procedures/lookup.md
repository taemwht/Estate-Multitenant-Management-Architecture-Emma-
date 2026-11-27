# Procedure: Lookup / List Tenants (REWRITTEN — "who lives where" is now multi-step)

Read-only. No confirmation required.

## Resolving a single tenant by name
Match on `name` (exact, then fuzzy/partial if no exact match — `list_tenants(name=...)`
does a partial match server-side). If multiple tenants share a similar
name, list matches and ask which one — there's no house/unit context to
narrow it by anymore at the tenant level (see below for why).

## "Who lives at [house/unit]?" — now a chained lookup, not a direct query
This used to be a direct query on `tenants.house_id`. It isn't anymore —
use `list_tenants_for_unit(unit_reference)`, which does the chain for
you: resolves the unit, finds its active lease(s), fetches the attached
tenants. Pass `active_only=False` for "show tenant history" (past/ended
leases included) instead of just who's there now.

- "Who lives at Claremont?" -> `list_tenants_for_unit("Claremont")`
- "Show tenant history for Claremont" -> `list_tenants_for_unit("Claremont", active_only=False)`
- "Who's in unit #A at Claremont?" — the old `unit_label` filter doesn't
  exist anymore. If a property has a distinct "#A" unit, it should be its
  own separate rental_unit record (see house-crud) with its own
  `unit_reference` — look it up by that reference directly rather than
  a label filter.

## "Show me evicted tenants"
Also chained now, not a direct tenant-status query — evictions are
recorded as `lease.end_reason = "eviction"` on ended leases. There's no
single `tenant_crud.py` function for "all evicted tenants across the
company" yet; if this comes up often, it's worth a small rent-crud
addition (filtering leases by end_reason) rather than approximating it
here.

## Co-tenants / "who else is on this lease"
Use `list_tenants_by_lease(lease_id)` if you already have the lease id
(e.g. from a `list_tenants_for_unit` result), or `get_leases_for_tenant(tenant_id)`
to go the other direction — find which lease(s) a given tenant is on.

Include soft-deleted tenants only if explicitly asked (and note:
`include_deleted` isn't wired up server-side yet — see `validation.md`).
