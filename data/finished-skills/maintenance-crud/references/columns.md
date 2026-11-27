# Fields — old-to-new mapping

| Old | New | Notes |
|---|---|---|
| `maintenance_request_id` | `id` (UUID) | Changed type. |
| `house_id` (int) | resolved via `unit_reference` -> `rental_unit_id` | Same pattern as house-crud/rent-crud. |
| `unit_label` | *(gone)* | Same reasoning as tenant-crud — separate rental_unit records now, not a tag. |
| `location_detail` | `location_detail` | Preserved — was missing from the first platform build, added migrating this skill. |
| `problem_description` | `description` | Renamed. |
| `priority` | `priority` | Preserved — same gap as above, added migrating this skill. |
| `status` | `status` | Values changed — see `validation.md`. |
| `reported_by_tenant_id` | `reported_by_tenant_id` | Preserved, but see note below — genuinely different from `submitted_by`. |
| `tenant_availability` | `tenant_availability` | Preserved. |
| `assigned_pit_crew_id` | `assigned_contractor_id` | Renamed, same soft-reference approach. |
| `scheduled_date` | `scheduled_date` | Preserved as a REAL date — the first platform build conflated this with a status-change timestamp; fixed. |
| `cost` | *(gone — see below)* | |
| `payment_method` | *(gone — see below)* | |
| `completed_date` | `completed_at` (automatic) | Set automatically when status becomes Completed — not something you pass in. |
| `is_deleted` | `is_deleted` (boolean, was 0/1) | |
| `modified_by` | *(gone — audit log)* | |

## `submitted_by` vs `reported_by_tenant_id` — not the same thing
`submitted_by` is whichever logged-in USER used the system to create the
request (could be staff, could eventually be a tenant with portal
access). `reported_by_tenant_id` is which TENANT the issue actually
concerns — the old system's exact distinction (null if landlord-
observed rather than tenant-reported). Both exist and mean different
things; don't conflate them.

## `cost` / `payment_method` — moved to a different skill entirely
Not just renamed — genuinely relocated. Recording what a repair cost is
now `pit-crew-crud`'s job (a `ContractorPayment` record, linked back to
this request via `maintenance_request_id`), not a field on the request
itself. See `procedures/complete.md` for how the two steps relate.

## Brand new
- `maintenance_log` table — didn't exist until this migration.
- `Verified` status step — no old equivalent (see `SKILL.md`).
