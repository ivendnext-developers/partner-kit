---
id: snap-ebt-at-the-till
title: SNAP and EBT benefits taken at the till
area: integrations
topic: payments-and-fiscal
asks: Our grocery customers pay with SNAP or an EBT card, only for the eligible items and with no sales tax on that part, and the rest on another way of paying
status: not-yet
door: request
blocked-by: product-work
recipe: none
sample: none
request: -
verified: written 2026-11-22 from the product's payments records · not run
---
## What you build
Nothing a partner can build today. A payment connector (`recipes/payment_connector.md`) takes the amount the till asks it for, and the till has no EBT way of paying: one held to the eligible items, with no sales tax on that part, the rest on another tender. That is ours, in the payments layer. The payer door (the card *insurance-co-payment*) does not fit: it is asked for a named customer, claims its share afterwards and takes no card swipe or PIN.

## Limits
- **Ask us:** an eligible-item flag and an EBT tender held to the eligible items, with no sales tax on that part. It has no date.
- The processor is a second piece: one that takes EBT cards. The US card terminal our payments app connects takes none. Once the till can hold a tender to the eligible items, an EBT-capable processor is a payment connector on your own server (the card *own-payment-connector*).
- Not run: nothing here has been built or tried.

## Tell the customer
SNAP and EBT cannot be taken at the iVendNext till today. We take the request and give no date.
