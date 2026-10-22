---
id: local-delivery-app
title: A local delivery app sent the orders to deliver
area: integrations
topic: online-shops-and-orders
asks: Send our delivery orders to our local delivery company's app and see where each one is
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/system_sync.md
sample: samples/s7_system_sync
request: -
verified: read 2026-10-22 in the system sync and event feed recipes · S7's pattern with a delivery app (orders out, status back) not built or run
---
## What you build
Your outside app on S7's pattern: it reads each order to deliver from the event feed, sends it to the delivery app, and writes the delivery's status back to the shop over the API.

## Limits
- Not run: no sample sends orders to a delivery app.
- The feed reports an order after it is booked, so the delivery app hears of it seconds later.
- The status lands where your app writes it (a field your manifest adds, or a record of your own), not on a screen the shop already has.

## Tell the customer
Orders to deliver reach your delivery company within seconds, and each order shows the status the delivery company reports.
