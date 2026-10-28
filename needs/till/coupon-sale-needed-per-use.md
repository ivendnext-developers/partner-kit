---
id: coupon-sale-needed-per-use
title: A coupon that needs a sale of a given size for each use
area: till
topic: payment
asks: One coupon for each so much spent; a coupon only on a sale above a minimum
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/coupon_rules.md
sample: samples/s32_coupon_rules
request: -
verified: 2026-10-28 · bench
related: coupon-first-purchase-or-group, coupon-uses-per-store, coupon-or-loyalty-cap
---
## What you build
Your service answers the check before payment. iVendNext keeps one rule per coupon with the sale each use needs; the service adds up the amounts of the coupons on the sale and refuses them when the sale's total is less. One coupon of 100 for each 1,000 spent is a rule of 1,000 on each such coupon: two need a sale of 2,000. With one coupon it is a minimum sale for that coupon.

## Limits
- Answered when the cashier presses Pay, not when the coupon is entered.
- The sale's total is as rounded for payment, after its discounts (the coupons' own included), tax included. An exchange's replacement is its own sale, judged at its own total.
- One amount per coupon, read in each sale's own currency.
- It counts each coupon as one use, never what the coupon takes off: a 10% coupon with 1,000 here takes 100 of a 1,000 sale, a 50% coupon 500. It is a minimum sale per coupon, not a cap on the discount.
- Several coupons of one kind on one sale count as one. For one coupon for each so much spent, give each coupon its own record and rule (coupons issued as serial numbers of one coupon cannot be used twice on a sale unless its hidden Can Repeat In Transaction is ticked, and then count once).
- Offline, the till does not ask the service: the coupon applies and the sale is flagged when it syncs.

## Tell the customer
A coupon on a sale too small for it is refused at Pay with the amount needed; the cashier removes a coupon or adds to the sale.
