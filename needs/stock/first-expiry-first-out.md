---
id: first-expiry-first-out
title: First-expiry-first-out at the till
area: stock
topic: batches-and-expiry
asks: The till sells the batch that expires first
status: ready-with-limits
door: configure
blocked-by: -
recipe: none
sample: none
request: -
verified: carried 2026-10-16 · not re-run (read in the product's `serial_batch.py` `list_lots` at POS origin/development 3a2335e0a; not walked on a till)
---
## What you build
Nothing of yours: switch batch tracking on for the item (card batches-and-expiry). At the batch pick the till lists the item's lots with the earliest expiry first, lots with no expiry last and empty lots at the bottom, and proposes the earliest-expiry lot or lots for the quantity, splitting across lots when one is short for a line in the stock unit (`list_lots`, `business_logic/serial_batch.py`).

## Limits
- The cashier confirms the pick: a proposal, not an assignment. The server checks the pick again at checkout and refuses one that does not add up to the quantity.
- A line sold in a pack unit takes one lot for the whole line: the earliest lot that holds it, or none.
- The order is by expiry date alone. It does not follow the shop's Stock Settings choice of first-in or first-expiry; a till that assigns lots by itself in that order is a product decision, not a door (ask us if the customer needs it).
- For an item that has both batches and serial numbers, the till books each unit with the batch its serial number carries from POS build 2.0.0.654; before that build the core's automatic pick of the first-in lot could override the proposal.
- Offline, a batch line is added without a pick (read in the till's code, not walked).

## Tell the customer
At the batch pick the till suggests the lot that expires first, and the cashier confirms it.
