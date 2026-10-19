---
id: prescription-before-payment
title: A prescription number before payment
area: till
topic: questions-during-the-sale
asks: A prescription number is required before a prescription item is paid for
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule_guard.md
sample: samples/s18_rule_guard
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Your service answers the check before payment and refuses the sale, with your sentence, while a prescription line has no prescription number.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.

## Tell the customer
A sale with a prescription item cannot be paid until its prescription number is recorded.
