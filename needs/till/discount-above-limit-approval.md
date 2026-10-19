---
id: discount-above-limit-approval
title: A discount above a limit needs a manager
area: till
topic: manager-approvals
asks: A discount above a set limit needs a manager's approval
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/till_guard.md
sample: samples/s23_till_guard
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service reads the sale's discounts in the check before payment and answers `approve` when one is above the limit.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- A manager who is not the cashier signs in on the till to approve. Approval by e-mail has no door.

## Tell the customer
A discount above the limit waits at Pay until a manager approves it on the till.
