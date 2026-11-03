---
id: head-office-bi
title: Head-office reports and BI
area: reports
topic: reports-and-bi
asks: Head-office reports and our BI tool fed with sales and stock
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/bi_feed.md
sample: samples/s9_bi_feed
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
An outside app on the feed and bulk reads fills the BI tool.

## Limits
- Rows are as of extraction: a later change to a booked sale, other than a return or a cancellation, is not followed.
- Offline sales arrive late, when the till syncs.

## Tell the customer
Head office sees sales and stock in its own BI tool, shortly after they are booked.
