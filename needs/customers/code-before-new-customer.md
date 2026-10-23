---
id: code-before-new-customer
title: A one-time code before a new customer is made
area: customers
topic: customer-records
asks: A one-time code sent to the customer before a new customer is made at the till
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/capture.md
sample: samples/s20_capture
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service is asked when a new customer is added; it sends a one-time code, and the server checks the code before the customer is made.

## Limits
- New customers only: an existing customer chosen for a sale is another event of the same door (the card *question-on-existing-customer*).
- Three wrong codes end the check, and a code lives ten minutes.

## Tell the customer
A new customer is made only after they read back the code sent to their phone.
