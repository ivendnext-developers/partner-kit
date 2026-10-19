---
id: erp-in-step-both-ways
title: The customer's own ERP kept in step both ways
area: integrations
topic: erp
asks: Our ERP and iVendNext kept in step: items, prices, stock and purchase orders
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/system_sync.md
sample: samples/s7_system_sync
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
Your outside app on the API and the event feed, keeping its own map of record ids, its own place in the feed, and a nightly reconciliation.

## Limits
- The feed reports a change after it is saved, so your app corrects after the fact.
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).
- Webhooks try three times, then stop: use the feed for anything you must not miss.
- One ERP per company.

## Tell the customer
The ERP and iVendNext stay in step within minutes, and a nightly pass reconciles them.
