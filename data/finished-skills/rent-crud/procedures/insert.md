# Procedure: Insert — Lease, Rent Change, or Payment

**All three require confirmation** — this is the one skill where Add is
never automatic, since these are commitments and money records.

## Creating a lease — the tenant-crud handoff completes here
This is where the two-step flow from tenant-crud's `procedures/insert.md`
finishes. By the time you're here, you should already have: a tenant id
(from tenant-crud), a unit reference, a start date, and a rent amount —
either parsed from the original request or asked for if missing.

1. Confirm you have: `unit_reference`, at least one `tenant_id`,
   `start_date`, `monthly_rent`, `due_day_of_month`. Ask for anything
   missing — don't guess.
2. Show a confirmation summary, e.g.:
   > "Create lease for John Smith at Claremont (#A), starting 2026-09-01,
   > $2,900/mo due on the 1st, $2,900 security deposit. Confirm?"
3. On explicit yes, call `create_lease()`. If it fails because the unit
   already has an active lease, relay that plainly — don't retry
   automatically or guess at a workaround.
4. Report back the new lease's id.

## Recording a rent change
1. Resolve the lease (`procedures/lookup.md`) via unit or tenant name if
   not already known.
2. `effective_date` is **required** — if not given, ask immediately:
   "Effective starting when?" Do not proceed without an answer.
3. Show a confirmation summary, e.g.:
   > "Set rent for [tenant/lease] at $3,000/mo, due on the 1st, effective
   > 2027-01-01. Confirm?"
4. On explicit yes, call `record_rent_change()`. Unlike the old system,
   there's no separate "supersede the old agreement" step to remember —
   the API handles both the history entry and the lease's current rate
   together.

## Logging a payment
1. Resolve the lease.
2. Parse `amount_paid`, `date_paid`, `payment_method`, `late_fee` per
   `references/nlp-parsing.md`. Remember `payment_method` is now
   constrained to `check`/`cash`/`other` — anything else goes in `notes`.
3. Show a confirmation summary, e.g.:
   > "Log $1,500 payment from [tenant] on 2026-07-29 (Venmo, noted), no
   > late fee. Confirm?"
4. On explicit yes, call `insert_rent_payment()`.

## Compound example — full flow across two skills
> "John Smith rented Claremont #A starting Sept 1 at $2,900, security
> deposit same amount"
1. (tenant-crud, if John doesn't exist yet) create the tenant -> got
   tenant_id
2. (rent-crud, here) `create_lease(unit_reference="Claremont",
   tenant_ids=[tenant_id], start_date="2026-09-01", monthly_rent=2900,
   due_day_of_month=<ask if not given>, security_deposit_amount=2900)`
   — confirm before writing, per above

**Note the loss of cross-skill atomicity:** if step 1 succeeds and step 2
fails (e.g. the unit already has an active lease), you'll have a
standalone tenant record with no lease. That's a real possibility now —
tell the user plainly if it happens rather than silently retrying or
leaving them unsure what actually got saved.
