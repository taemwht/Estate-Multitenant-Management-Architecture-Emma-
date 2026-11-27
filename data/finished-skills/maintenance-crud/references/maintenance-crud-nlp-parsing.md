# Parsing Freeform Maintenance Reports & Matching to a Contractor Trade

Same approach as before — agent-side reasoning, not code. Given:
> "My toilet flooded and the sink in the hall bathroom is backed up too,
> I'm home all week except Wednesday"

Extract:
- `unit_reference` — resolve from context (who's reporting, which
  property) or ask if ambiguous. (Was `house_id`/`unit_label` before.)
- `location_detail` — the specific room/fixture ("hall bathroom"). If
  genuinely two distinct problems, ask whether to file one request or
  two rather than silently merging or splitting.
- `problem_description` — keep the tenant's actual wording.
- `tenant_availability` — when they're reachable/home.
- `priority` — infer from severity ("flooded", "no heat", "gas smell" ->
  `emergency`) but don't downgrade something the tenant flagged as
  urgent. See `SKILL.md`'s emergency-handling note — an emergency
  priority logs the request AND tells the tenant to contact emergency
  services themselves; it is not the mechanism for handling a live
  emergency.

## Matching a Problem to a Contractor Trade
Not a stored field — reason directly from `problem_description` to a
trade value and call `suggest_contractors_for_trade()`:

- "toilet flooded", "sink backed up", "pipe leaking" -> `plumber`
- "no power", "outlet sparking", "breaker tripped" -> `electrician`
- "no heat", "AC not working", "furnace" -> `hvac`
- "fridge broken", "dishwasher not draining" -> `appliance`
- "locked out", "broken lock" -> `locksmith`
- "roof leak", "shingles" -> `roofer`
- "ants", "mice", "cockroaches" -> `pest_control`
- "overgrown yard", "sprinklers" -> `landscaping`
- Unclear ("door won't close", "squeaky stair") -> `handyman`/`general`

If nothing matches, say so plainly and ask who to assign — never guess a
person, never silently create a contractor record to work around a
missing match.

Same parse-before-write pattern as `tenant-crud` and `rent-crud`.
