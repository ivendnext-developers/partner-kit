---
id: line-quantity-cap
title: A limit on the quantity of one item on a line
area: till
topic: limits-on-a-sale
asks: No more than 50 of one item on a line
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/till_guard.md
sample: samples/s23_till_guard
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
Your service answers the check before payment and refuses a sale with a line over the limit, in your own sentence. The limit lives in one settings record the shop edits.

## Limits
- Answered when the cashier presses Pay, not when the quantity is typed.

## Tell the customer
The till stops the sale at Pay when a line is over the limit and tells the cashier why. It does not stop the quantity being typed.
