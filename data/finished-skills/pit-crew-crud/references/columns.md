# Fields — old-to-new mapping

| Old | New | Notes |
|---|---|---|
| `contractor_id` | `id` (UUID) | Changed type. |
| `first_name` + `last_name` | `name` | Same pattern as tenant-crud. |
| `primary_trade` | `trade` | Renamed. Same fixed values, still enforced. |
| `preferred_payment_method` | `preferred_payment_method` | Preserved — was missing from the first platform build, added migrating this skill. |
| `phone` | `contact_phone` | Renamed. |
| `email` | `contact_email` | Renamed. |
| `notes` | `notes` | Preserved — same gap, added migrating this skill. |
| `is_deleted` | `is_deleted` (boolean, was 0/1) | |
| `modified_by` | *(gone — audit log)* | |

## The trade vocabulary — fixed values, enforced again
Exactly: plumber, electrician, hvac, handyman, roofer, appliance,
locksmith, pest_control, landscaping, general, other. Same list as
before. Worth knowing: during the initial platform build this had
quietly become unconstrained free text, which caused a real mismatch
bug with maintenance-crud's trade-matching (it used "plumbing" instead
of "plumber") — both are now fixed and the database enforces the list
again.

## Brand new
contractor_payments — cost used to live directly on
maintenance_requests; it's a separate, linked entity now. See SKILL.md.
