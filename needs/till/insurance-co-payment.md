---
id: insurance-co-payment
title: An insurance co-payment at the till
area: till
topic: payment
asks: Insurance co-payment: the insurer pays part of a prescription and the customer the rest
status: not-yet
door: request
blocked-by: extension-point
recipe: recipes/third_party_payer.md
sample: samples/s43_third_party_payer
request: P-PAYER
verified: 2026-10-23 · tests (the rules, claims, remittances) · not run (the door)
---
## What you build
A payer service: its payers, plans, formularies and members as records in the shop; claims made from the sales the
POS app's payer door books, filed as a file, matched to the payer's remittance. Start from [S43](../../samples/s43_third_party_payer/README.md)
and its recipe, [Third-party payer](../../recipes/third_party_payer.md).

## Limits
- **Waits on us:** the payer door in the POS app (request P-PAYER): the payer's share booked as owed by the payer,
  coverage asked line by line before the tender, the claim reference and the split on the receipt, a return giving the
  payer's share back. Until it is there, nothing is sold on a payer.
- **Online only**, one payer per sale.

## Tell the customer
The records and the claims can be set up now; selling on a payer comes with the POS app's payer door.
