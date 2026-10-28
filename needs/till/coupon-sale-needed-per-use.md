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
verified: 2026-10-28 · laptop tests
related: coupon-first-purchase-or-group, coupon-uses-per-store, coupon-or-loyalty-cap
---
## What you build
Your service answers the check before payment. iVendNext keeps one rule per coupon with the sale each use needs; the service adds up the amounts of the coupons on the sale and refuses them when the sale's total is less. One coupon of 100 for each 1,000 spent is a rule of 1,000 on each such coupon: two need a sale of 2,000. With one coupon it is a minimum sale for that coupon.

## Limits
- Answered when the cashier presses Pay, not when the coupon is entered.
- The sale's total is after its discounts, the coupons' own included, and tax included.
- The check sees each coupon once, so a coupon allowed to repeat on one sale counts once.
- Judged on a sale, not on a return or an exchange with nothing owed.
- Offline, the till does not ask the service: the coupon applies and the sale is flagged when it syncs.

## Tell the customer
A coupon on a sale too small for it is refused at Pay with the amount needed; the cashier removes a coupon or adds to the sale.
