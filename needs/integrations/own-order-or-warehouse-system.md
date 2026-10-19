---
id: own-order-or-warehouse-system
title: The customer's own order or warehouse system
area: integrations
topic: online-shops-and-orders
asks: Our order-management or warehouse system linked to the stores
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Your outside app over the API and the event feed; the customer's systems stay its own, and you connect to them.

## Limits
- The feed reports a change after it is saved, so your app corrects after the fact.
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).

## Tell the customer
The order and warehouse systems exchange records with iVendNext through our app.
