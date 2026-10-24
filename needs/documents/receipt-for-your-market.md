---
id: receipt-for-your-market
title: A receipt laid out for your market
area: documents
topic: receipts
asks: A receipt with our logo, tax number and address, a line per VAT rate, in a second language
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/receipt_format.md
sample: samples/s4_receipt_pack
request: -
verified: 2026-10-16 · 0.1.2 printed the same figures as 0.1.1 on our sandbox (standard, zero-rated, mixed); returns, charges, discount or rounding, the till's Print sheet and UAE's own tax field not run there
popular: yes
---
## What you build
A print format installed by a manifest (or set up by hand), then chosen on the till's POS Profile, which is configuration. The save is refused if it cannot print the register's latest sale. The format reads only the sale; the sample's package adds one field to the sale that copies the Company's tax ID.

## Limits
- The format is for the till sale only; a back-office invoice has its own.
- A sale saved before the package was installed has no tax number on it; the address is the one the sale holds, from the POS Profile or the Company.
- Two different non-zero rates under one tax account print a single VAT total.
- Arabic on paper or PDF, a returned sale and a sale with two or more tax rows: not run.
- A customised receipt gets none of our later fixes, and the retailer's seeded receipt carries more than the sample (per-item charge rows, serial and batch lines, deposit and balance lines, offline-sale lines): copy back what your market needs.

## Tell the customer
The receipt carries the retailer's logo, tax number, address and a line per VAT rate; we test returns and your language before go-live.
