---
id: react-to-sales-and-stock
title: Your system told of sales, returns and stock moves
area: integrations
topic: events
asks: Our system hears about every sale, return and stock move
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
An outside app reads the event feed and reacts to each sale, return and stock move.

## Limits
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).
- Webhooks try three times, then stop: use the feed for anything you must not miss.
- An offline sale's events appear when the till syncs, possibly hours later.

## Tell the customer
Your system hears of each sale, return and stock move shortly after it is saved.
