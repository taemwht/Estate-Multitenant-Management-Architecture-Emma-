# Procedure: Update — Lease, Rent Agreement, or Payment

**Confirmation required.** Show before/after and wait for explicit yes.

## The core distinction, unchanged from the old system
Prefer recording a NEW rent change (`record_rent_change`, see
`procedures/insert.md`) over editing an existing rate row in place,
*except* to fix a genuine data-entry error (wrong amount typed, wrong
due day) on a row that hasn't been followed by a later change yet. If
the change reflects an actual rent change over time, that's
`record_rent_change`, not `update_rent_agreement`.

## Ending a lease — this is where eviction status lives now
"[Tenant] moved out [date]" or "[Tenant] was evicted" is `end_lease()`,
not a tenant-crud operation (tenants don't have a status field anymore —
see tenant-crud's migration notes). Resolve the lease first, then:
> "End [tenant]'s lease at [unit], effective 2026-11-15, reason: eviction.
> Confirm?"
On yes, call `end_lease(lease_id, end_date, end_reason)`. Leave
`end_reason` off (or use "normal") for an ordinary move-out.

## Correcting a payment
For fixing a data-entry error (wrong amount, date, method) on an
existing payment row — `update_rent_payment()`. Show before/after,
confirm, then write.

## Correcting a lease record itself
For fixing a typo on deposit amount, dates, etc. that ISN'T a rent
change — `update_lease()`. Show before/after, confirm.
