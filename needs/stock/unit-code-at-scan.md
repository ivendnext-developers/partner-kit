---
id: unit-code-at-scan
title: A unit's own code recognised at the scan
area: stock
topic: handheld-and-scanning
asks: Scan a unit's own barcode or a handset's tag, and refuse a unit already sold
status: ready-with-limits
door: scan-source
blocked-by: -
recipe: recipes/unit_codes.md
sample: samples/s19_unit_codes
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
The retailer declares a table of its units' own codes; the till's scan finds the unit, its batch and serial, and refuses one already sold. It is data: no code runs.

## Limits
- A unit sold on another till a moment before: not run in the kit (the product's own tests cover it).
- When the code must be checked on Desk documents too (receipts, transfers, counts), make it a serial number instead: the card units-as-serial-numbers, sample S30. This card's scan source stays for codes a retailer keeps in its own table.
- A batch-and-serial unit is booked at the till with the batch its serial number carries from POS build 2.0.0.654; before it, a unit sold reliably only from the lot iVendNext picks first.

## Tell the customer
Scanning a unit's own code finds that exact unit, and a unit already sold is refused.
