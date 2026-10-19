---
id: no-placeholder-price
title: No line sold at a placeholder price
area: till
topic: limits-on-a-sale
asks: No line at a placeholder price such as 0.01
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/till_guard.md
sample: samples/s23_till_guard
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service answers the check before payment and refuses a sale while any line carries the placeholder price, with your own sentence.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.

## Tell the customer
A sale with a line at the placeholder price cannot be paid; the cashier is told to correct the price first.
