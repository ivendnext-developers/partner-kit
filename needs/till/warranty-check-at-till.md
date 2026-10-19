---
id: warranty-check-at-till
title: A warranty check at the till
area: till
topic: questions-during-the-sale
asks: Check a product's warranty at the till
status: ready-with-limits
door: till-key
blocked-by: -
recipe: recipes/point_handler.md
sample: samples/s1_warranty
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
A till key calls your service with the sale's lines; your service answers with the warranty, as a message the cashier reads.

## Limits
- Till keys answer online only: the key is dimmed on an offline till.
- When your service is down, a press tells the cashier it could not finish, nothing is added, and the sale goes on.
- The key's request carries no money and no serial numbers: read them from the booked sale, after it is booked.

## Tell the customer
The cashier presses a key to see the warranty for the items in the sale, while the till is online.
