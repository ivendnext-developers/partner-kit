---
id: room-charge-opera-cloud
title: Charge a meal to a guest's room on OPERA Cloud
area: integrations
topic: outside-systems
asks: Put a meal or a drink on the guest's room at the hotel, with OPERA Cloud as our hotel system
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/room_charge.md
sample: samples/s63_room_charge
request: -
verified: read from the vendor's public documents 2026-11-08 · the adapter is not built; start from S63's Mews adapter
---
## What you build
An adapter for S63, one file with two calls (`find` and `post`), beside `service/hotel_mews.py`. What OPERA Cloud asks for: an OPERA Cloud Foundation subscription, an integration platform subscription and a registered application. Daily, fetch the food and beverage transaction codes and the cashier id, which every post must carry. Find the occupied room with `getRooms` and `getReservations`; post with `postBillingCharges` against the reservation id, as the final amount per revenue code.

## Limits
- A vendor's guide says the reservation's posting-restriction flag is not enforced by the API, so your adapter must read it.
- OPERA's on-site interface (FIAS) is not researched: no public specification was found. This card covers OPERA Cloud's API only.
- The till books first and the folio follows within about a minute, so a charge the hotel then refuses waits on the auditor's list.
- A return is posted as a negative amount per revenue code; confirm that your property allows it.

## Tell the customer
Your server types the room and surname, a wrong room is stopped at Pay, and the charge reaches the guest's OPERA folio within about a minute. Your partner builds the OPERA link on our free starter.
