---
id: local-delivery-app
title: A local delivery app sent the orders to deliver
area: integrations
topic: online-shops-and-orders
asks: Send our delivery orders to our local delivery company's app, or our own runner at the airport who brings an order to the gate, and see where each one is
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/system_sync.md
sample: samples/s7_system_sync
request: -
related: duty-free-allowance-and-boarding-pass
verified: read 2026-10-22 in the system sync and event feed recipes · S7's pattern with a delivery app (orders out, status back) not built or run; gate limit added 2026-11-22, not run
---
## What you build
Your outside app on S7's pattern: it reads each order to deliver from the event feed, sends it to the delivery app, and writes the delivery's status back to iVendNext over the API.

## Limits
- Not run: no sample sends orders to a delivery app.
- An airport store's own runner is the same route, with the runner's app as the delivery app. The boarding pass is on the sale by the card *duty-free-allowance-and-boarding-pass*; the gate is a value on the sale (the card *value-asked-at-till*) or a field of your own, and changes after the order are your app's to follow. Not run.
- The feed reports an order after it is booked, so the delivery app hears of it seconds later.
- The status lands where your app writes it (a field your manifest adds, or a record of your own), not on a screen the retailer already has.

## Tell the customer
Orders to deliver reach your delivery company within seconds, and each order shows the status the delivery company reports.
