---
id: reason-codes
title: A coded reason for a void, a return or a discount
area: till
topic: cash-voids-returns
asks: A coded reason when a cashier voids, returns or discounts
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: samples/s5_config_pack
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Reason Code Master rows and the switch for each type in Retail Setting (a void reason also needs `save_voided_transaction`).

## Limits
- The till asks for the reason, but the server does not insist: a sale discount with no reason code still books.
- Item-return and sale-return reasons: not run.
- Offline: not run.

## Tell the customer
The cashier picks a coded reason for each void, return and discount, and the reason is kept on the sale.
