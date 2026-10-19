---
id: own-events-feed
title: A feed of your own app's events
area: integrations
topic: events
asks: Our app gets its own queue of what changed, with business labels
status: ready-with-limits
door: event-feed
blocked-by: -
recipe: recipes/event_feed.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
The event feed extension point: your app pulls its own queue (sales, customers, stock) and marks each item done.

## Limits
- The kit's feed client and its samples have not been run against this extension point: not run.

## Tell the customer
Your app reads its own queue of changes and nothing is lost while it is down.
