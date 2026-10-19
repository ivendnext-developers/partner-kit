---
id: low-stock-reminder
title: A reminder for each store when stock is below its level
area: stock
topic: alerts-and-reorder
asks: A reminder per store when its stock falls below a set level
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: none
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 · the reorder job made a submitted transfer request for one item below its level; not run: the e-mail on creation, the report *Itemwise Recommended Reorder Level* with sales in range (it returned no rows)
---
## What you build
Item Reorder rows on the item (the store, the level, the quantity, the type *Transfer* or *Purchase*) and the setting for automatic requests in Stock Settings; the standard job makes the request.

## Limits
- The request is submitted, never a draft (run: type *Transfer* made a submitted *Material Transfer* request, status Pending); for a draft see the card stock-and-expiry-alerts.
- Leave the row's warehouse group empty: with a group named, the level is compared with the whole group's stock and a store below its level was not reordered (run).
- The job runs once a day over the whole site, only while the automatic-request setting is on (it is off until someone switches it on: read on the sandbox); it covers every item with a reorder row.
- The quantity requested is the reorder quantity, or the shortfall when that is larger, and it compares projected stock, so an open request or an incoming order delays the next one (read from the code).

## Tell the customer
Each store's low stock comes as a transfer request, raised once a day; it is a real request, not a draft.
