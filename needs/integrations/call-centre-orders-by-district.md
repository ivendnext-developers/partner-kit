---
id: call-centre-orders-by-district
title: Phone orders sent to the store that serves the customer's district
area: integrations
topic: online-shops-and-orders
asks: Our call centre takes orders by phone; each order should go to the store that serves the customer's district
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/call_centre_orders.md
sample: samples/s35_call_centre_orders
request: -
verified: 2026-10-21 · bench
---
## What you build
A Serving store field on the retailer's own Territory tree (a district's store, or the store of the territory above it), and a button on a draft sales order, *Send to store*, answered by your service: it walks the order's territory up the tree, checks the store's warehouse, and writes it on the order and on every line. The store then sees the order in its own list.

## Limits
- An agent presses the button: an order is not routed on its own when it is saved.
- The territory is the customer's: an order for another district needs its territory changed before the press.
- Drafts only, one order at a time; a submitted order is cancelled and amended to move it.
- The service reads the whole order and writes it back: the app's user needs read and write on every sales order and read on every customer, territory and warehouse.
- A store's own tax or prices can change the total when the warehouse changes; the agent is told.
- A store with a User Permission on its warehouse still sees an order whose Set Source Warehouse is empty.
- No notice to the store: its filtered list is its inbox.

## Tell the customer
Your call centre enters each phone order once, presses one button, and the order ships from the store that serves the customer's district.
