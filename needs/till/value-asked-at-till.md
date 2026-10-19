---
id: value-asked-at-till
title: A value asked for at the till
area: till
topic: questions-during-the-sale
asks: An answer for the cashier during the sale: a message, or a seal number, a reference or a warranty card number added to the sale
status: ready-with-limits
door: till-key
blocked-by: -
recipe: recipes/point_handler.md
sample: samples/s1_warranty
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
A key on the till calls your service; your answer is a message, details added to the sale, values for its lines, or any of them together.

## Limits
- The cashier presses the key: nothing makes the cashier press it.
- Till keys answer online only: the key is dimmed on an offline till.
- The key's request carries no money and no serial numbers: read them from the booked sale, after it is booked.

## Tell the customer
The cashier presses a key to record the value on the sale. It is not forced, and it needs a connection.
