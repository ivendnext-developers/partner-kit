---
id: coupon-on-parent-group
title: A coupon or promotion that covers every group under a parent item group
area: prices
topic: promotions
asks: A coupon for Supplements should cover every supplement, Protein and Vitamins included
status: ready-with-limits
door: event-feed
blocked-by: -
recipe: recipes/parent_groups.md
sample: samples/s31_parent_groups
request: -
verified: sample S31's laptop tests and canaries only (13 tests, 9 canaries); not run on a retailer's iVendNext: the till applying a written-out coupon was not walked
related: prices-promotions-coupons
---
## What you build
The till's coupon and promotion engines match an item's own item group exactly, so a row naming a parent group misses its children. An outside app on the event feed writes a coupon's get rows and a promotion's exclusion rows out as the child groups, and keeps them so when a group is added or moved.

## Limits
- A row appears a few seconds after the save, not in the same save.
- A promotion's buy and get rows are reported, never changed: a child row there would change the offer.
- A coupon has no item-group exclusions at this version.
- Every item group save reads every coupon and promotion: with thousands of them, run the catch-up on a schedule instead.
- Not run on a till.

## Tell the customer
A coupon or promotion set on a parent group covers every group under it, kept up to date a few seconds after each change.
