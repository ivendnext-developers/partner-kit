---
id: own-loyalty-earning
title: Loyalty earned in the customer's own programme
area: customers
topic: loyalty-and-wallets
asks: Every booked sale earns loyalty points in our own programme
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/customer_owned_loyalty.md
sample: samples/s22_customer_loyalty
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
The customer's service reads each booked sale from the feed and credits its own ledger; the ledger may live in iVendNext as your manifest's records.

## Limits
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).
- Loyalty points are credited when the service is back: a sale waits in the feed while it is down.

## Tell the customer
Each booked sale earns in your own programme, shortly after it is booked.
