---
id: room-charge-mews
title: Charge a meal to a guest's room on Mews
area: integrations
topic: outside-systems
asks: Put a meal or a drink on the guest's room at the hotel, with Mews as our hotel system
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/room_charge.md
sample: samples/s63_room_charge
request: -
verified: Mews Demo environment 2026-11-08 (a guest found by room and surname; a charge, a negative line and a two-line order posted) · laptop tests
---
## What you build
Nothing new: the sample ships this adapter. The server types the room and surname on the check's Sale details; at Pay the check finds the guest with Search customers and fills the reservation on the sale; within about a minute of the sale booking the worker posts it with Add order, each line on an accounting category you choose, the receipt number in its notes, linked to the reservation.

## Limits
- The till books first and the folio follows within about a minute (two when the shop's worker is busy), so a charge the hotel then refuses waits on the auditor's list.
- Mews' *No Post* classification (`Cashlist`) does not block an order, so the adapter reads it at Pay and again at the post.
- A posted item cannot be cancelled: a return is a negative line. Confirm that your property allows rebates.
- An order has no idempotency key: a call whose answer was lost goes to the auditor, never again to Mews.
- Room numbers may hold letters; the room is matched as typed.
- The tip is a separate line on the hotel's tip code. iVendNext books nothing for it, so the till's tips report does not see it.

## Tell the customer
Your server types the room and surname, a wrong room is stopped at Pay, and the charge reaches the guest's Mews bill within about a minute. Your night auditor reads one list of anything Mews refused.
