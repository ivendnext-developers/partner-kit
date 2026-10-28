---
id: coupon-uses-per-store
title: A coupon used at most so many times in each store
area: till
topic: payment
asks: A coupon can be redeemed only so many times in a store
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: none
request: -
verified: carried 2026-10-28 · not re-run (read in the engine's and the POS app's code)
related: coupon-sale-needed-per-use, prices-promotions-coupons
---
## What you build
A setting in iVendNext Desk, no app. On the **Coupon**, set *Maximum Redemption Count Per Store*: once that many of the store's sales carry the coupon, the till refuses it with *Coupon has reached its maximum redemption limit.* when the cashier applies it. 0 is no limit.

## Limits
- Counted per store, over the store's sales that carry the coupon.
- Offline, the till does not apply a coupon with this limit.
- A cap on every store together, or per customer, is not this setting (one use per customer is the Coupon's *Apply Once Per Customer*, hidden on its form until shown with *Customize Form*).

## Tell the customer
Each store stops a coupon once it has been used the number of times you set.
