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
- A phone that also has a batch (a lot): from POS build 2.0.0.654 the till books each phone with the batch its serial number carries, and refuses one whose serial number has no batch (the card *units-as-serial-numbers*, sample S30). Before that build, it sells reliably only from the lot iVendNext picks first.
- Offline: not run.

## Tell the customer
The till asks for the IMEI of each phone sold and refuses one already sold.
