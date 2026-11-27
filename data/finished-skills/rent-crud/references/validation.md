# Validation Rules — Leases, Rent History, Payments

## Creating a lease (`create_lease`) — NEW, no old equivalent
- `unit_reference` — must resolve to an existing rental unit. If
  ambiguous/not found, stop and ask.
- `tenant_ids` — at least one required; each must be an existing,
  non-deleted tenant (create via tenant-crud first if they don't exist).
- `start_date`, `monthly_rent`, `due_day_of_month` — all required.
- The unit must not already have an active lease — the API enforces
  this and returns a clear error if violated; you don't need to
  pre-check it yourself.

## Recording a rent change (`record_rent_change`)
- `effective_date` — **required, never defaulted to today.** If the user
  doesn't specify one when changing rent, ask immediately: "Effective
  starting when?" Do not proceed without an answer. (Unchanged from the
  old system's rule.)
- `monthly_rent`, `due_day_of_month` — required.
- Unlike the old system, there's no `status` flag to manage — the change
  is simply the newest entry by `effective_date`; nothing needs marking
  as "superseded."

## Logging a payment (`insert_rent_payment`)
- `amount_paid`, `date_paid` — required.
- `payment_method` — **now constrained** to `check`/`cash`/`other`. If
  the user says "Venmo" or similar, either map it to `other` and put the
  actual method in `notes`, or just put it directly in `notes` — don't
  invent a new method value, the API will reject anything outside the
  three.
- `late_fee` — defaults to 0 if not mentioned.
- Conversational amounts ("fifteen hundred") must be parsed to numbers
  first — see `references/nlp-parsing.md`. Never store the raw phrase.

## Data-entry corrections (`update_lease`, `update_rent_agreement`, `update_rent_payment`)
For fixing a typo on an existing record — NOT for recording a genuine
change over time. See `procedures/update.md` for the distinction and
when to use which.

## Defaults
- `is_deleted`: false on insert.
- `late_fee`: 0 if not specified.
- `modified_by`: no longer applies (see `SKILL.md`).

## Lease/tenant resolution
`lease_id` must correspond to an existing lease. Resolve via
`resolve_lease_for_unit()` or `resolve_lease_for_tenant_name()` rather
than guessing — if either comes back with more than one active lease
(shouldn't normally happen given the one-active-lease-per-unit rule, but
`resolve_lease_for_tenant_name` can return multiple if someone's on more
than one lease), stop and ask which one.
