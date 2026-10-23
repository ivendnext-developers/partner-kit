---
id: prescription-before-payment
title: A prescription number before payment
area: till
topic: questions-during-the-sale
asks: A prescription number is required before a prescription item is paid for
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/pharmacy_counter.md
sample: samples/s39_pharmacy_counter
request: -
verified: 2026-10-22 · bench
---
## What you build
Drug schedules, pharmacists and prescriptions as the retailer's own records, and a service that answers the check before payment and the Desk's document checks. A prescription line is paid only against a prescription for this customer, in date for its class, with a fill and quantity left; the fill is reserved when the check answers, so two tills cannot both spend the last one. A pharmacist-only line is paid only by a pharmacist whose licence is in date; a controlled line needs the customer's identity fields; caps per sale and per patient hold; dispensed medicine is refused at a return and on a Desk credit note.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- The till cannot ask for the patient's identity when it adds a customer: it is entered on the Desk.
- A POS Invoice made on the Desk POS screen, or through the API, is not checked.
- A POS day left open holds its reserved fills until it closes.
- At most three checks per POS Profile, 10 seconds together; this app takes one per profile.

## Tell the customer
A sale with a prescription item cannot be paid until a pharmacist sells it against a valid prescription for that customer, and the same holds for sales orders, deliveries and invoices on the Desk.
