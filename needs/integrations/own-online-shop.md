---
id: own-online-shop
title: The customer's own web store
area: integrations
topic: online-shops-and-orders
asks: Orders from our own web store, subscription orders too, come in; stock and prices go out
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run; subscription limit added 2026-11-22, not run
---
## What you build
Your outside app: orders in, stock and prices out.

## Limits
- An online order cannot be edited at the till.
- A subscription or auto-replenish plug-in is the web store's own, and the kit has no route for a subscription. Your app brings each order the plug-in places in as it brings any order; a renewal order it makes on its own is not run.

## Tell the customer
Online orders arrive in iVendNext and the web store shows the stores' stock and prices.
