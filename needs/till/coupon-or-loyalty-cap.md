---
id: coupon-or-loyalty-cap
title: A cap on what a coupon or a loyalty points balance may pay
area: till
topic: payment
asks: A coupon or a loyalty points balance pays no more than part of the sale
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule_guard.md
sample: samples/s18_rule_guard
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service answers the check before payment and refuses, or leaves out the payment method, when the coupon or balance would pay over the cap. For a wallet you run yourself, the wallet's own answer carries the cap (the card *store-wallet-at-till*).

## Limits
- Answered when the cashier presses Pay, not when the line is entered.

## Tell the customer
The till stops a coupon or a loyalty balance from paying more than the agreed share, at Pay.
