---
id: extra-fields-on-shop-documents
title: Extra fields on the retailer's own documents
area: documents
topic: own-records-and-fields
asks: Extra fields on a purchase order and its lines, a goods receipt, a stock transfer, an expense or the till close
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/manifest.md
sample: none
request: -
verified: 2026-11-22 · iVendNext's own checker as the kit copies it (build 2.1.0.726) run on a manifest with a required field: accepted on a Purchase Order, refused on a POS Invoice and on a Sales Invoice; not installed on a site
popular: yes
---
## What you build
A manifest adds fields, named with your prefix, to the retailer's own record types and their child tables.

## Limits
- The checker refuses *required*, *unique* and *default* on a field only on the stock and accounting ledger entries and the till's own records (a sale, an order, a delivery, a payment, a journal entry, a customer, a contact, an address), so a field on a Purchase Order, a goods receipt or a stock transfer may be required in the manifest (`"reqd": 1`). An update cannot make an already installed field newly required: add a new field, or use a save rule (the card *required-when-another-filled*).

## Tell the customer
The documents carry the extra fields; a rule that a field must be filled is a separate save rule.
