---
id: room-charge-cloudbeds
title: Charge a meal to a guest's room on Cloudbeds
area: integrations
topic: outside-systems
asks: Put a meal or a drink on the guest's room at the hotel, with Cloudbeds as our hotel system
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/room_charge.md
sample: samples/s63_room_charge
request: -
verified: read from the vendor's public documents 2026-11-08 · the adapter is not built; start from S63's Mews adapter
---
## What you build
An adapter for S63: one file with two calls (`find` and `post`) beside `service/hotel_mews.py`, a line in `ADAPTERS` and its name in the manifest's *Hotel system* list. Look the guest up with `getReservations`, listing only checked-in guests; a `pos-room-charge` field set to *No* blocks charges and the API enforces it. Post with `postCustomItem`.

## Limits
- A newer check-posting endpoint exists and is not evaluated here: read it first.
- Cloudbeds says a refund can't be posted through its API. A return uses `postVoidItem` on the item's own id, one whole item at a time: your adapter keeps each line's id (S63 keeps a reference per line), and a partial return goes to the auditor.
- Charges reach only the primary guest's folio.
- Cloudbeds' POS category has a certification list. Taxes and `itemCategoryName` are mandatory and tips go on a separate line, so your adapter must add the tax itself.

## Tell the customer
Your server types the room and surname, a wrong room is stopped at Pay, and the charge reaches the guest's Cloudbeds folio within about a minute. Your partner builds the Cloudbeds link on our free starter.
