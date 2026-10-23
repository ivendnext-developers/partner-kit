---
id: own-online-shop
title: The customer's own web store
area: integrations
topic: online-shops-and-orders
asks: Orders from our own web store come in; stock and prices go out
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Your outside app: orders in, stock and prices out.

## Limits
- An online order cannot be edited at the till.
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).

## Tell the customer
Online orders arrive in iVendNext and the web store shows the stores' stock and prices.
