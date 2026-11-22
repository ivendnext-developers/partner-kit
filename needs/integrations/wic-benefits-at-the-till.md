---
id: wic-benefits-at-the-till
title: WIC benefits taken at the till
area: integrations
topic: payments-and-fiscal
asks: Our grocery customers pay with WIC (eWIC), each state's approved products only
status: not-yet
door: request
blocked-by: product-work
recipe: none
sample: none
request: -
verified: written 2026-11-22 from the product's payments records · not run
---
## What you build
Nothing a partner can build today. WIC is taken through a processor that each state certifies, with each state's own product list: the partner's and the processor's work. It also needs the till work of the card *snap-ebt-at-the-till*, which is ours: an eligible-item flag and a tender held to the eligible items.

## Limits
- **Ask us:** the same till work as the card *snap-ebt-at-the-till*. It has no date.
- Each state's product list and its certification of a processor are the processor's and the partner's, state by state, not iVendNext's. A processor reaches the till as a payment connector on your own server (the card *own-payment-connector*), once the till can hold a tender to the eligible items.
- Not run: nothing here has been built or tried.

## Tell the customer
WIC cannot be taken at the iVendNext till today. The till work is ours and has no date; each state certifies the processor that takes it.
