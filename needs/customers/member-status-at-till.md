---
id: member-status-at-till
title: A member's status at the till
area: customers
topic: loyalty-and-wallets
asks: Show the member's tier and status when the cashier asks
status: ready-with-limits
door: till-key
blocked-by: -
recipe: recipes/point_handler.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
A till key answered by the customer's own service, with a message the cashier reads.

## Limits
- Till keys answer online only: the key is dimmed on an offline till.
- The key's request carries no money and no serial numbers: read them from the booked sale, after it is booked.

## Tell the customer
The cashier presses a key to see the member's status, while the till is online.
