# Procedure: Delete (Soft) / Restore Tenant

**Confirmation required for delete.** Restore does not require confirmation.

Note: soft-deleting a tenant is different from moving a tenant out (that's
now a rent-crud lease update — see `procedures/update.md`). Delete here
means removing the tenant record from default views entirely (e.g. it
was added in error).

## Delete Steps
1. Resolve the target tenant.
2. Call `delete_tenant(tenant_id)` — **do not pre-check anything
   yourself.** The rent-history check now happens INSIDE this function
   (client-side, in `tenant_crud.py` itself — the API doesn't enforce
   this), not something you compute separately beforehand.
3. If it returns a warning dict (`{"warning": "rent_history_attached", ...}`),
   relay it to the user, e.g.:
   > "This tenant has 14 rent payment records across their lease(s) —
   > deleting will keep that history but mark the tenant record inactive.
   > Continue?"
   On explicit yes, call `delete_tenant(tenant_id, force=True)`.
4. If it returns `None` with no warning, the tenant is already deleted —
   nothing further to confirm.

## Restore Steps
1. Resolve the target tenant among soft-deleted tenants.
2. Call `restore_tenant(tenant_id)`. No confirmation required.
