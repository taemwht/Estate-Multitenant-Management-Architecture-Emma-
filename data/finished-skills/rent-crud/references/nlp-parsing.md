# Parsing Conversational Payment Info

Unchanged in approach from before — this is agent-side reasoning, not
code. Given something like:
> "John paid fifteen hundred today, rest next week"
> "Got $2,800 from the Claremont tenant via Venmo, no late fee"

Extract:
- `amount_paid` — convert spoken/written amounts to a plain number
  ("fifteen hundred" -> `1500`, "$2,800" -> `2800`). Never store the raw
  phrase.
- `date_paid` — default to today if the user says "today" or gives no
  date; otherwise resolve to `YYYY-MM-DD`.
- `payment_method` — pull directly from what's mentioned, but remember
  the new system only accepts `check`/`cash`/`other` as the actual
  `method` value (see `validation.md`) — if something else is
  mentioned ("Venmo"), put the real value in `notes` and pass `other` (or
  the closest of the three) as `payment_method`.
- `late_fee` — only set if explicitly mentioned; otherwise 0.
- **Leftover context** that isn't a DB field (e.g. "rest next week")
  should NOT be silently discarded. Either put it in `notes`, and/or
  echo it back to the user as a confirmation/follow-up.

This mirrors the same parse-before-insert pattern used in `tenant-crud`.
