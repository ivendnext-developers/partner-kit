---
id: imei-per-phone-sold
title: The IMEI of every phone sold, once
area: stock
topic: handheld-and-scanning
asks: Record the IMEI of every phone sold, and never sell one twice
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: samples/s5_config_pack
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
The item's Has Serial No: the IMEI is the serial number, received with the stock. The shop needs a default Company.

## Limits
- A phone that also has a batch (a lot): until P-SERIALUNITS (one row per serial with its own batch at the till) ships, the till sells reliably only from the lot iVendNext picks first (sample S30).
- Offline: not run.

## Tell the customer
The till asks for the IMEI of each phone sold and refuses one already sold.
