# Parsing Freeform Tenant Info

Mostly unchanged from before — this is agent-side reasoning, not code, so
the parsing approach itself doesn't change. What changed is WHAT you do
with the parsed result: `unit_label` and `move_in_date` are no longer
things you pass to `insert_tenant()` (see `procedures/insert.md`) — you
still may need to parse them out of the user's message, just to hand off
to rent-crud afterward instead of tenant-crud.

Given something like:
> "Add John Smith to unit #A at Claremont, 510-555-1234, john@email.com,
> moving in Sept 1"

Extract:
- `first_name`, `last_name` — split on the last whitespace-separated
  token as last name, everything before as first name, unless the name
  is clearly not "first last" (only one name given — leave `last_name`
  null rather than guessing). **Only these two go to `tenant_crud.py`.**
- `unit_label`/unit reference ("#A", "Claremont") and `move_in_date`
  ("Sept 1") — extract these too, but they're NOT tenant-crud inputs.
  Hold onto them for the rent-crud step that creates the lease (see
  `procedures/insert.md` for the full two-step flow).
- `phone` — pull out anything that looks like a phone number; store as
  given (free text, no reformatting required, strip obvious filler like
  "my number is").
- `email` — pull out anything containing `@` and a domain.

If `first_name` can't be confidently extracted, ask rather than guessing
or inserting a blank value.

This same parse-before-insert pattern applies to `rent-crud`'s
`amount_paid` field (e.g. "fifteen hundred" -> `1500`) — see that skill's
`references/nlp-parsing.md`.
