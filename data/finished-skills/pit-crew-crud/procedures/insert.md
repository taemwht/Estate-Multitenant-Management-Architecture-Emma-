# Procedure: Insert Pit Crew Member

No confirmation required before saving.

## Steps
1. Parse `first_name`, `last_name`, `phone`, `email` from the message
   (same freeform-extraction approach as `tenant-crud`).
2. Map the described trade to a `primary_trade` value. Ask only if
   genuinely ambiguous.
3. `preferred_payment_method`, `notes`: free text, capture if given.
4. Call `insert_pit_crew()`. Report back the new contractor's name and
   trade.

## Example
> "Add Bob Alvarez, he's a plumber, 510-555-9876, pays through Venmo"
-> primary_trade="plumber" -> insert_pit_crew(first_name="Bob",
   last_name="Alvarez", primary_trade="plumber", phone="510-555-9876",
   preferred_payment_method="Venmo")
