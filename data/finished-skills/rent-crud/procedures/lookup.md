# Procedure: Rent Lookups

Read-only. No confirmation required.

## Resolving a lease
- By unit: `resolve_lease_for_unit(unit_reference)` — active lease by
  default; pass `active_only=False` for history including ended leases.
- By tenant name: `resolve_lease_for_tenant_name(name)` — can return more
  than one lease if the person is on multiple; if so, list them and ask
  which one applies.
- A request phrased at the house/unit level ("update Longford rent") must
  resolve to the specific active lease first. If more than one plausible
  match exists, stop and ask — never silently apply a change to an
  arbitrary lease.

## "Who owes what" — pick the right one of two functions
- **This month only, quick check** — `rent_status(lease_id)`. Use for
  "is [tenant] paid up," "how much is still owed this month."
- **Full picture, multiple months** — `arrears(lease_id)`. Use for "how
  much total does [tenant] owe," "what about last month too," or any
  question implying more than the current month. Returns `total_owed`,
  `total_paid`, `credit_balance` and a month-by-month breakdown. Each
  month is priced at the rate in effect on its due date. Payments are
  pooled and applied oldest month first, so a payment made on Aug 2 for
  July pays off July, and an overpayment shows up as `credit_balance`
  (money the tenant is ahead) rather than vanishing. A month's `paid` is
  the amount applied to it, not what was received during it. The
  current month only counts once its due date has passed.

Don't default to `rent_status` for a question that's actually asking
about accumulated/historical owing — that function only ever looks at
the current month and will understate the real answer.

## "Who owes what" — portfolio-wide
Run `arrears()` (or `rent_status()` if only this month matters) across
every active lease. Only flag leases with a nonzero outstanding amount
unless the user asks for the full list.

## Rent history for a lease
`get_rent_history(lease_id)` — ordered newest first. Report each amount
and when it took effect, e.g. "$2,600 from Jan 2024, raised to $2,800
effective Jan 2025, currently $2,900 as of Sept 2026."

## Payment history for a lease
`list_payments_for_lease(lease_id)`, ordered by date.

Include soft-deleted rows only if explicitly asked.
