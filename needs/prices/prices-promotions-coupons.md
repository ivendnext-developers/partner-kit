---
id: prices-promotions-coupons
title: Prices, promotions and coupons
area: prices
topic: promotions
asks: Our prices, promotions and coupons
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: samples/s31_parent_groups
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Set up in iVendNext Desk: price lists, promotions and coupons. No code.

## Limits
- Combined discounts follow the promotion rules.
- Offline, pricing rules are not applied.
- A coupon or promotion row naming a parent item group matches only items placed directly in it. Sample S31's service writes a coupon's get rows and a promotion's exclusion rows out as the child groups; a promotion's buy and get rows are reported, never changed, as a child row there would change the offer.

## Tell the customer
Prices, promotions and coupons are set up in iVendNext; how discounts combine follows its promotion rules.
