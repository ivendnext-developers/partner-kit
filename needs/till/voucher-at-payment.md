---
id: voucher-at-payment
title: A partner's voucher or PIN made at payment and printed on the receipt
area: till
topic: payment
asks: A partner's voucher or PIN made when the sale is paid and printed on the receipt
status: ready-with-limits
door: fulfil-at-sale
blocked-by: -
recipe: contracts/pages/partner_fulfil.md
sample: none
request: -
verified: run by the product 2026-10-18 (POS train T12's walk, phone, counter and tablet frames: the receipt waits then prints the code, down then Try again then print without it, a refusal, a refund refused until the code is cancelled, a cancelled sale's codes voided, offline refused); not run by a kit sample
---
## What you build
A service for the *fulfil at sale* extension point: after the sale is paid and booked, the shop's server asks it once per sold line of the items you name (by item group or an item field), and your answer's code prints under the item on the receipt, its reprints and the gift receipt. Before that line is refunded, the shop asks your service to cancel the code. The kit's stand-in voucher service (`contracts/extension_contracts/standins/voucher_service.py`) keeps both promises: the same key always returns the same code, and a cancel wins over any later issue.

## Limits
- One code per line: the till sells such an item one per line, and a line of more than one cannot be sold at the till.
- Sold and paid at the till only: refused on a quote, an order, a layaway plan, a held sale and offline.
- When your service is slow or down the sale stands and the receipt waits; the cashier can print without the code and reprint later. A refund waits until the code is cancelled.
- A shop's own print format prints the code only if it reads it under each item, as the shipped formats do; a receipt sent by text message carries no code.
- A Desk credit note against the day's roll-up invoice is checked by item, not by line: cancel the code first, then raise the credit note.

## Tell the customer
The till asks our service for the voucher or PIN as soon as the sale is paid and prints it on the receipt; a refund of that line cancels the code with us first.
