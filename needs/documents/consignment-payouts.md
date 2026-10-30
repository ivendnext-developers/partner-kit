---
id: consignment-payouts
title: Consignment payouts
area: documents
topic: own-records-and-fields
asks: Each consignor's share of the pieces sold, worked out from the till and Desk sales, returns taken off, and each sale paid once
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/consignment_payouts.md
sample: samples/s61_consignment_payouts
request: -
verified: 2026-10-30 · laptop
---
## What you build
A consignor as your manifest's own record type, with the share each piece pays them; a field on Item naming its consignor and, where it differs, its own share. A payout per consignor with two Desk buttons whose service reads the retailer's own till sales and Desk invoices: one writes every sold line no other payout holds (returns negative, the share and the consignor's part on each), the other checks every line again before it moves the payout to Paid, a step your workflow lets only your app's own role take. A save rule then locks the paid payout, so no line is ever paid twice.

## Limits
- The share is the one on the item or the consignor when the payout is worked out; a change before *Pay* makes *Pay* refuse until it is worked out again.
- Payouts are worked out by a press, one consignor at a time, at most 500 lines a payout.
- How the consignor is paid (cash, a transfer, store credit) is recorded on the payout; booking it in the accounts is a version of your own.

## Tell the customer
Each consignor's payout is worked out from your own sales with returns taken off, checked again before it is marked paid, and no sale is ever paid twice.
