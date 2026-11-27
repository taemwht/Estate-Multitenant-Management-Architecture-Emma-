# Procedure: Insert Tenant (REWRITTEN — tenant and lease are now separate steps)

No confirmation required before saving the tenant record itself — but
freeform input must be parsed first (`references/nlp-parsing.md`).

**Read this before anything else:** inserting a tenant here ONLY creates
the person record (name, email, phone). It does NOT attach them to a
house/unit, set a move-in date, or create anything lease-related. If the
user's request implies housing someone ("add John to unit #A, moving in
Sept 1"), that's a TWO-SKILL operation now:
1. `tenant-crud` creates the person (this file's job)
2. `rent-crud` creates the lease, attaching this tenant's id, with the
   unit, move-in date, and rent amount — see rent-crud's
   `procedures/insert.md` for that half

## Steps for the tenant-crud half
1. Parse `first_name` (required), `last_name`, `phone`, `email` from the
   user's message per `references/nlp-parsing.md`. Also parse out any
   unit/move-in-date info mentioned — you'll need it for step 3, even
   though it's not a `tenant_crud.py` argument.
2. If `first_name` can't be confidently extracted, ask rather than
   guessing or inserting a blank value.
3. Call `insert_tenant()`. Report back the new tenant's name and id.
4. If the user's request implied housing this tenant somewhere (a unit
   was mentioned), continue immediately into rent-crud's insert flow
   using the new tenant's id, the parsed unit reference, and the parsed
   move-in date/rent info — don't stop and make the user ask separately
   unless something's missing and needs clarifying first.

## Example
> "Add John Smith to unit #A at Claremont, 510-555-1234, john@email.com,
> moving in Sept 1, rent is $2900"
1. Parse: first_name="John", last_name="Smith", phone="510-555-1234",
   email="john@email.com" -> `insert_tenant(...)` -> got tenant_id
2. Parsed but held for step 2: unit="Claremont", unit_label="#A",
   move_in_date="2026-09-01", monthly_rent=2900
3. Hand off to rent-crud: create a lease for that unit with this
   tenant_id, start_date=2026-09-01, monthly_rent=2900 (confirming with
   the user per rent-crud's own confirmation requirement — Add always
   requires confirmation there, unlike here)

> "Add a tenant named Priya, no other details yet"
-> first_name="Priya" -> insert_tenant("Priya") -> report back the new
   tenant id. Nothing to hand off to rent-crud since no unit/lease was
   implied — this one really is just a person record for now.
