---
id: minimum-selling-price-approval
title: Selling below the minimum price needs a manager
area: till
topic: manager-approvals
asks: Selling below the minimum price needs a manager's approval
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/till_guard.md
sample: samples/s23_till_guard
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service compares each line's price with the minimum in the check before payment and answers `approve` when one is below it.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- A manager who is not the cashier signs in on the till to approve. Approval by e-mail has no door.

## Tell the customer
A sale with a line below the minimum price waits at Pay until a manager approves it on the till.
