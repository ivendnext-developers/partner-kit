---
id: coupon-first-purchase-or-group
title: A coupon for a first purchase only, or for one customer group
area: till
topic: payment
asks: A coupon only a new customer may use, or only customers of one group
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/coupon_rules.md
sample: samples/s32_coupon_rules
request: -
verified: 2026-10-18 · bench
---
## What you build
Your service answers the check before payment. iVendNext keeps one rule per coupon; the service refuses the coupon when the sale's customer has bought before (a first-purchase coupon) or is not in the coupon's customer group.

## Limits
- Answered when the cashier presses Pay, not when the coupon is entered.
- Offline, the till does not ask the service: the coupon applies and the sale is flagged when it syncs.
- The check does not run on a park to a till, a layaway deposit, an account collection or the Desk's own POS screen: a restricted coupon there is neither refused nor flagged.
- The count is taken at the check: a sale for the same customer booked after the check and before the money is not seen.
- A customer group matches exactly: a group under it is not the same group.
- The app's user needs a plain read on the retailer's sales and no User Permissions, or a returning customer can pass as new.

## Tell the customer
A restricted coupon is refused at Pay with the reason; the cashier removes it and the sale goes on.
