---
id: products-on-promotion-colour
title: A coloured row for products on promotion in the Desk list
area: prices
topic: promotions
asks: A coloured row in the Desk product list for the products on promotion
status: not-yet
door: request
blocked-by: extension-point
recipe: none
sample: none
request: P-LISTMARK
verified: run on a sandbox 2026-10-16 · POS 2.0.0.645 · the item has no status field to colour a row from; not run: a workflow set in Desk
---
## What you build
Nothing yet: the Desk list colours a row only from the record's own status, and the item has none.

## Limits
- A field of your own cannot take the place of a status, and a manifest cannot add a workflow to a shop's own record types (chapter 7); a workflow set in Desk was not run.
- Today (not run) the filter and the saved view of the card products-on-promotion-filter list the same products.

## Tell the customer
The Desk list cannot yet colour the products on promotion; it can filter and list them.
