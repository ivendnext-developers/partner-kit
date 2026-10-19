---
id: pharmacy-pack-code-at-scan
title: A pharmacy pack's 2D code read at the scan
area: stock
topic: batches-and-expiry
asks: Read a pharmacy pack's 2D code at the scan, and refuse an expired pack
status: ready-with-limits
door: scan-source
blocked-by: -
recipe: recipes/unit_codes.md
sample: samples/s19_unit_codes
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
The till reads the pack's GS1 code (item, batch, expiry, serial) at the scan. It is data: no code runs.

## Limits
- GS1 codes: not run in the kit (the product's own tests cover them).
- A pack's own serial checked on Desk documents too (receipt, transfer, count): the card units-as-serial-numbers, sample S30; at the till only from the lot iVendNext picks first until P-SERIALUNITS (one row per serial with its own batch at the till) ships.

## Tell the customer
The till reads the pack's code, finds the batch, and refuses an expired pack.
