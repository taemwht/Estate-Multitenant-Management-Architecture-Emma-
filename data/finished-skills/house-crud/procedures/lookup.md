# Procedure: Lookup / List Houses

Read-only. No confirmation required. Unchanged from before the 2026-08
migration — the underlying mechanism moved from a direct database query
to an API call, but nothing about how you should behave here changed.

## Resolving a single house
Match on `nickname` (exact, then fuzzy if no exact match) — this is the
primary way users refer to a house conversationally. If ambiguous (e.g.
multiple close fuzzy matches), list the options and ask which one.

## Listing houses
- "Show me all houses" -> list all non-deleted houses.
- "What units are at [address]?" -> filter by `street_address` — this is
  the way to see all units sharing one physical property (e.g. #A and #B
  both at "138 Longford Drive").
- Include soft-deleted houses only if the user explicitly asks for
  deleted/inactive/historical records. (Note: as of the 2026-08
  migration, `include_deleted` isn't fully wired up server-side yet — if
  a user explicitly asks for deleted records and none come back, say so
  rather than reporting "none exist.")

## Multiple units at one address
Since a single street address can now have more than one house row (one
per unit), if a user's question is ambiguous about which unit they mean
("what's the rent at 138 Longford"), list all units at that address and
ask which one, rather than guessing or only returning the first match.
