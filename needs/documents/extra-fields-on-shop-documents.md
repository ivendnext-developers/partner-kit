---
id: extra-fields-on-shop-documents
title: Extra fields on the shop's own documents
area: documents
topic: own-records-and-fields
asks: Extra fields on a purchase order and its lines, a goods receipt, a stock transfer, an expense or the till close
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/manifest.md
sample: none
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
A manifest adds fields, named with your prefix, to the shop's own record types and their child tables.

## Limits
- A manifest cannot make such a field required, unique or defaulted: use a save rule (the card *required-when-another-filled*).

## Tell the customer
The documents carry the extra fields; a rule that a field must be filled is a separate save rule.
