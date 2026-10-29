---
id: reservations-and-waiting-list
title: Reservations, a waiting list and seating that opens the table's check
area: customers
topic: history-and-crm
asks: A restaurant's bookings and walk-ins kept by the host, a table never booked twice, a text when a table is ready, and seating that opens the table's order on the till
status: ready-with-limits
door: open-check
blocked-by: -
recipe: recipes/front_of_house.md
sample: samples/s55_front_of_house
request: -
verified: 2026-10-29 · bench
related: open-check-from-an-app
---
## What you build
A reservation and a waiting-list entry as your manifest's own record types, the guest's name, phone, customer and notes limited to a host role your app's own user does not hold. Desk buttons answered by your service: *Book* holds the table against overlapping bookings, *Seat* opens the party's check at its table through the till's open-check door (`check_open`, a key written on the record first so a retry opens one check), *Change booking*, *No-show* and *Cancel booking* release it. *Table ready* is the retailer's own SMS Notification. A deposit is the till's customer advance, linked from the booking.

## Limits
- The guard runs at *Book* and *Seat*; the form keeps a booked slot read-only, the list's *Edit* and the API do not.
- The app opens checks and reads the floor, nothing more: dishes, moves, payment and the close stay at the till.
- Before the app is removed, every check it opened is paid or closed: the uninstall removes its user.

## Tell the customer
Your hosts keep the bookings and the waiting list in iVendNext, a table is never booked twice, guests get a text when their table is ready, and one press seats a party with its table open on every till.
