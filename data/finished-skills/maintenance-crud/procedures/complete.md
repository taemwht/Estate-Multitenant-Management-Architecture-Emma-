# Procedure: Complete Maintenance Request

**Confirmation required.** The one write in `maintenance-crud` that
always requires an explicit yes.

## Steps
1. Resolve the target request. Normally `In Progress` at this point, but
   allow completing from any non-terminal status if the user says the
   job's done.
2. Show a summary and wait for explicit yes, e.g.:
   > "Mark the flooded toilet at Claremont complete? (status only — cost
   > isn't tracked here anymore, see below.) Confirm?"
3. On explicit yes, call `update_request(request_id, status="Completed")`.
4. On anything other than a clear yes, do not write.

## Cost and payment — a separate step now, not gated together
The old system required `cost` in the same call as marking something
complete. The new platform decouples these on purpose: `Completed` here
means "the physical work is done," full stop. If the user also gives a
cost/payment method, that's a **separate** action via `pit-crew-crud`
(recording a `ContractorPayment` linked to this request's id) — offer to
do that too if they've given the info, but don't block completing the
request on it being present.

Example:
> "Bob fixed the toilet, cost $180, paid via Venmo"
1. Confirm + call `update_request(request_id, status="Completed")`.
2. Then (pit-crew-crud): record the $180 payment to Bob, linked to this
   request — a second, related but independent step.
