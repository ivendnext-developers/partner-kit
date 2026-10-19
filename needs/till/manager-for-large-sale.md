---
id: manager-for-large-sale
title: A manager's approval for a large sale
area: till
topic: manager-approvals
asks: A manager must approve a sale over a set amount
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
Your service answers the check before payment with `approve` when the sale is over the amount; the till asks a manager before it takes payment.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- A manager who is not the cashier signs in on the till to approve. Approval by e-mail has no door.

## Tell the customer
A sale over the amount waits at Pay until a manager signs in on the till and approves it.
