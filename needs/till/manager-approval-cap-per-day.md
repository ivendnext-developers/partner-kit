---
id: manager-approval-cap-per-day
title: No more than so many manager approvals for a discount per store per day
area: till
topic: manager-approvals
asks: No more than so many manager discount approvals per store per day
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/till_guard.md
sample: samples/s23_till_guard
request: P-OVERRIDECAP
verified: carried 2026-10-16 · not re-run; the count itself is not built or run
---
## What you build
Your service counts approvals for each store and day in the check before payment: it answers approve until the limit is reached, then refuse. Count a sale once, not each time it is asked.

## Limits
- Answered when the cashier presses Pay, not when the discount is typed. The check is asked again for the same sale when the basket changed or Pay is pressed again, so count approvals per sale, and a sale abandoned after an approval still used one.
- It counts the approvals your own check asked for. The till's own approval inbox is a separate path that this check does not count (not run): ask which path the shop's managers use (P-OVERRIDECAP would count the inbox).
- Offline the till uses your declared down answer.

## Tell the customer
After the day's limit of manager approvals for a store, a further discount is refused at Pay; we count only the approvals our check is asked about.
