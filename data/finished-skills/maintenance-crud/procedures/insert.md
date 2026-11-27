# Procedure: Insert Maintenance Request

No confirmation required before saving — but freeform input must be
parsed first (`references/nlp-parsing.md`).

## Steps
1. Resolve `unit_reference` (and confirm which unit if ambiguous).
2. Parse `location_detail`, `problem_description`, `tenant_availability`,
   `priority` from the report.
3. If from a known tenant, set `reported_by_tenant_id`; leave null if
   landlord-observed.
4. `status` defaults to `Submitted`. Do NOT set `assigned_contractor_id`
   or `scheduled_date` at insert time even if the user already knows who
   they want — that's a separate update step, keeping insert focused on
   intake.
5. Call `insert_request()`. Report back a summary.

## Emergency reports — handle carefully
If the report reads as a genuine emergency (gas smell, no heat in
freezing conditions, security issue): set `priority: emergency`, log the
request as normal, AND tell the tenant plainly to contact 911 or their
utility's emergency line themselves. Do not supply a specific phone
number or improvise safety steps — see `SKILL.md`'s emergency-handling
note for why. The logged request is for follow-up/tracking, not for
resolving a live emergency.

## Example
> "My toilet flooded and the sink in the hall bathroom is backed up too,
> I'm home all week except Wednesday"
-> unit resolved -> location_detail="hall bathroom" ->
   problem_description="Toilet flooded, sink backed up" ->
   tenant_availability="Home all week except Wednesday" ->
   priority="high" (flooding, not quite emergency-tier) ->
   insert_request(unit_reference="Claremont", problem_description=...,
   location_detail="hall bathroom", priority="high",
   reported_by_tenant_id=<id>, tenant_availability=...)

> "I smell gas in the kitchen"
-> priority="emergency" -> insert_request(...) -> tell the tenant
   directly: "That needs immediate attention — please contact your gas
   utility's emergency line or 911 right now. I've logged this as an
   emergency request for follow-up."
