# Procedure: Delete (Soft) / Restore

**Confirmation required for delete.** Restore does not require confirmation.

Applies to rent-rate-history rows and payment (rent-receipt) rows — not
leases themselves (there's no lease-delete; a lease is ended via
`end_lease()`, not deleted — see `procedures/update.md`).

## Delete Steps
1. Resolve the target rate-history or payment row.
2. Show the matched record and ask for confirmation, e.g. "Delete this
   $1,500 payment from John Smith dated 2026-07-29?"
3. On explicit yes, call `delete_rent_agreement(lease_id, history_id)`
   or `delete_rent_payment(payment_id)`.

Note: deleting a rate-history row is different from a rent decrease — if
rent is actually going down, record a new change (preserves history)
rather than deleting the old row. Delete is for correcting genuine
errors (e.g. a duplicate entry), same distinction as before.

## Restore Steps
1. Resolve the target row among soft-deleted records.
2. Call `restore_rent_agreement(...)` or `restore_rent_payment(...)`. No
   confirmation required.
