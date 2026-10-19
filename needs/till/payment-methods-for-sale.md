---
id: payment-methods-for-sale
title: Only some payment methods for a sale or a customer
area: till
topic: payment
asks: No store credit for a walk-in customer, no on-account for a cash customer, and methods that may not be combined
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule_guard.md
sample: samples/s18_rule_guard
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
Your service answers the check before payment with `allow` and `exclude_tenders`: the payment methods this sale may not use.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- The excluded methods show dimmed, with your reason.

## Tell the customer
At Pay the till offers only the payment methods this sale and this customer may use; the others are dimmed with the reason.
