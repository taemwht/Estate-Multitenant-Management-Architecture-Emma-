# Procedure: Insert House

No confirmation required before saving (once all required fields are
present) — but **required fields must be collected first**, since the
script will error (not gracefully) if any are missing.

## Required fields — ask if missing
Before calling `insert_house`, check that you have all of:
- `nickname` — must also be unique (now scoped per-company rather than
  across everyone — not a practical difference for single-company use);
  if the user's proposed nickname already exists, tell them and ask for
  a different one rather than attempting the insert (it will fail).
- `street_address`
- `city`
- `zip_code`

If any of these are missing from what the user gave you, **ask for all of
the missing ones in a single combined question** rather than one at a
time, e.g.:
> "To add this house I still need: the ZIP code and the city. What are those?"

Do not attempt the insert until all four are known. Do not guess or
default any of them.

## Strongly encouraged — ask once, don't demand
- `unit` — if the property might have multiple units at the same address
  (e.g. the user mentions "#A", "apartment", "unit"), ask for it. If the
  user is clearly describing a single-unit property, it's fine to leave
  blank without asking.

## Optional — mention once, don't insist
After collecting the required fields (and `unit` if relevant), it's fine
to ask once, briefly, whether the user wants to add any of:
- `bedrooms`, `bathrooms`, `year_built`, `status`, `notes`

e.g. "Want to add bedroom/bathroom count, year built, or any notes? Or I
can just save it as-is." If the user declines or doesn't answer, proceed
without them — do not ask again on this same insert.

## Multiple units at one address
If the user is adding a second (or third) unit at an address that already
has a house record (e.g. adding "#B" after "#A" already exists), this is
still a **new** house row — a new `insert`, not an update to the existing
one. Each unit is its own row with its own `nickname`, sharing the same
`street_address`.

## Steps
1. Collect required fields (ask if missing, per above).
2. Check nickname uniqueness (the script does this too, but check first to
   give a clean error message rather than a raw exception).
3. Ask once about `unit` if relevant, and once about optional details.
4. Call `insert_house`. Report back the new house's `id` and `nickname` —
   note the id is now a UUID string (e.g.
   `5e779923-f029-4635-8211-bbb795a91f6d`), not a small number like
   before, so don't invent a short-form id when reporting it back.

## Example
> "Add a house at 138 Longford Drive, unit B, South San Francisco, 94080,
> call it Longford B"
-> all required fields present (nickname="Longford B",
   street_address="138 Longford Drive", city="South San Francisco",
   zip_code="94080") + unit="#B" given -> check nickname uniqueness ->
   ask once about bedrooms/bathrooms/notes -> insert -> confirm back,
   e.g. "Added Longford B (138 Longford Drive, #B)."

> "Add a house, 555 Oak St"
-> missing nickname, city, zip_code -> ask: "To add this house I still
   need a nickname to call it, the city, and the ZIP code. What are
   those?" -> wait for answer before inserting.
