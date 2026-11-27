# Fields — old-to-new mapping

## Rent agreements -> rent rate history
| Old (`rent_agreements`) | New | Notes |
|---|---|---|
| `rent_agreement_id` | `id` (UUID) | Changed type. |
| `lease_id` | `lease_id` (real FK to a real lease now) | No longer a loose text label. |
| `monthly_rent_amount` | `monthly_rent` | |
| `rent_due_day` | `due_day_of_month` | Renamed. |
| `effective_date` | `effective_date` | Unchanged, still always required. |
| `status` (active/superseded) | *(gone)* | "Current" = whichever row has the latest `effective_date` — no separate flag to keep in sync. |
| `modified_by` | *(gone — audit log)* | |

## Rent payments -> rent receipts
| Old (`rent_payments`) | New | Notes |
|---|---|---|
| `rent_payment_id` | `id` (UUID) | Changed type. |
| `lease_id` | `lease_id` | Real FK now. |
| `amount_paid` | `amount` | Renamed. |
| `date_paid` | `date_received` | Renamed. |
| `payment_method` | `method` | **Now CHECK-constrained** to `check`/`cash`/`other` — free text like "Venmo" goes in `notes` or maps to `other`. |
| `late_fee` | `late_fee` | Same, unchanged — this field didn't exist in the new schema until this migration added it back. |
| `notes` | `notes` | Unchanged. |
| `is_deleted` | `is_deleted` (boolean, was 0/1) | Same meaning. |
| `modified_by` | *(gone — audit log)* | |

## Brand new — no old equivalent
- **Lease itself** (unit, dates, monthly_rent, due_day_of_month, status,
  end_reason, tenant_ids) — see house-crud/tenant-crud's notes on why
  this is now a first-class entity `rent-crud` creates.
- **`arrears()`** — multi-month total-owed tracking with correct
  historical rate application. The old system had no equivalent; it only
  tracked "current agreement minus payments since due date" for one
  period at a time.

## Required-field behavior
Same requirements as before: `effective_date` on a rent change is always
required, never defaulted to today — ask if not given. `amount_paid`/
`amount` and `date_paid`/`date_received` required on a payment.
