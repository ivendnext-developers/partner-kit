---
id: guest-ordering-qr-and-kiosk
title: Guests order from a QR code at the table or a kiosk, onto the table's check
area: customers
topic: history-and-crm
asks: A QR code on each table that opens the menu on the guest's phone, a self-order kiosk at the counter, and the orders on the till for staff to send and take payment
status: ready-with-limits
door: open-check
blocked-by: -
recipe: recipes/guest_ordering.md
sample: samples/s56_guest_ordering
request: -
verified: 2026-10-29 · bench
related: open-check-from-an-app
---
## What you build
A code record per table and per kiosk, its signed link and QR picture written by your service when the manager presses *Make code*, and a print format for the table card. A page your service serves: the register's own menu (its item groups, prices and the dishes' choice groups) and *Send order*. The order goes to the table's check through the till's open-check door (`check_open` when none is open, `check_add_lines` to the one that is), unsent, under a course of its own; a kiosk order opens a tab named by an order code, paid at the counter.

## Limits
- The app never sends to the kitchen, prices or takes a payment: the server sends, the till prices and pays.
- One order a table at a time; a table with more than one bill open, or one being paid, is refused.
- The till shows a guest's lines under their course and note, not as the guest's.
- No pictures, allergens or *sold out* on the menu in this version.

## Tell the customer
Your guests order from their phone at the table or at a kiosk; their orders appear on the table's bill on every till, your staff send them to the kitchen, and the bill is paid at the till as usual.
