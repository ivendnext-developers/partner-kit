---
id: question-on-existing-customer
title: A question when an existing customer is chosen
area: customers
topic: customer-records
asks: A question or a check when the cashier picks an existing customer for the sale
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/capture.md
sample: none
request: -
verified: run by the product 2026-10-16 · POS train T11's walk on three till frames (allow, refuse, a one-time code, the service down, offline); not run with a kit sample
---
## What you build
A capture on the event *customer select*: when the cashier puts an existing customer on a sale (picked, scanned, or brought by a resumed sale, a quote or an exchange), your service allows, refuses (the customer is taken off the sale) or sends a one-time code. The server holds every door that charges or books the sale until it has your pass for that cashier, customer and store.

## Limits
- Never asked for the store's walk-in customer, or for a customer this cashier added in the last ten minutes while a customer-add service is on.
- A payment pressed before your answer arrives is refused; the cashier picks the customer again.
- A payment on something the customer already holds (a layaway's later payment, an order's balance, their account) is not held.
- One cashier sends at most 60 select rounds in ten minutes.
- Offline you are not asked: the declared down answer applies, and the sale is flagged when it syncs.
- No kit sample yet: the recipe and the product's contract are the guide.

## Tell the customer
When the cashier picks a customer, your system can check them first: a customer locked to another store is taken off the sale, and a loyalty account can ask for a code.
