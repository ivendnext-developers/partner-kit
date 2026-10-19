---
id: own-crm
title: The customer's own CRM kept up to date
area: customers
topic: history-and-crm
asks: Our CRM sees our customers and their sales
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Your outside app reads customers and sales over the API and the feed and writes them to the CRM.

## Limits
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).
- The feed reports a change after it is saved, so your app corrects after the fact.

## Tell the customer
The CRM receives customers and sales shortly after they are saved.
