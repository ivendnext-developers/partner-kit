---
id: line-detail-for-goods
title: One more detail on a line
area: till
topic: questions-during-the-sale
asks: One more detail on a line, for goods with no serial number
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: samples/s5_config_pack
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
A Transaction Item Attribute: a name, a pattern and an order. The till offers it on each line.

## Limits
- The pattern is checked on the till screen only: the server accepts a value that breaks it.
- Offline: not run.

## Tell the customer
The till asks for the extra detail on each line and keeps it with the sale.
