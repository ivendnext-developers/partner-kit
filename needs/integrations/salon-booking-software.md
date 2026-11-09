---
id: salon-booking-software
title: The chain's booking software told about the sale
area: integrations
topic: outside-systems
asks: A customer books a brow, a makeover or a salon appointment in our booking software, and the sale at the till reaches it
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-11-09 · not re-run
---
## What you build
Your outside app, on the API and the event feed, between the chain's booking software and iVendNext. The service is an item sold at the till, with the advisor named on the sale and a tip taken at Pay; your app reads the sale after it is saved and marks the booking paid in the booking software, and can read the chain's customers and items to keep the two lists alike.

## Limits
- The booking itself lives in the booking software: iVendNext holds no calendar, no chair or room, and no reminder to the customer.
- The feed reports a sale after it is saved, so the booking software is told after the fact, not before the customer pays.
- A deposit taken at booking is the booking software's, and reaches iVendNext only as a payment your app records.
- A salon software vendor's own partner programme may have terms for connecting.

## Tell the customer
The service is sold at the till as usual; the booking software marks the appointment paid within minutes of the sale.
