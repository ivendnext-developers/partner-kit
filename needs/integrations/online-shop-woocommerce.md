---
id: online-shop-woocommerce
title: A web store on WooCommerce
area: integrations
topic: online-shops-and-orders
asks: Our WooCommerce web store linked to the stores, with its subscription orders
status: ready-with-limits
door: our-connector
blocked-by: -
recipe: guide/10_integrations.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run; subscription limit added 2026-11-22, not run
---
## What you build
Our WooCommerce connector: online orders in, stock and prices out. Ask us which release carries it for the customer.

## Limits
- It does not reserve stock.
- It takes percentage vouchers only.
- A subscription or auto-replenish plug-in is the web store's own, and the kit has no route for a subscription. Each order the plug-in places is a web order; a renewal order it makes on its own is not run.

## Tell the customer
Our connector links the WooCommerce store; it does not hold stock for an order, and vouchers are percentages.
