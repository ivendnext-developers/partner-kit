---
id: sale-line-count-cap
title: A limit on the number of lines in one sale
area: till
topic: limits-on-a-sale
asks: No more than a set number of lines on one sale
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule_guard.md
sample: samples/s18_rule_guard
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service counts the sale's lines in the check before payment and refuses a sale over the limit, with your own sentence.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.

## Tell the customer
A sale with too many lines is stopped at Pay, with the reason; the cashier splits it.
