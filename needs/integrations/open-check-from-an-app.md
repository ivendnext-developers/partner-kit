---
id: open-check-from-an-app
title: An outside app opens a table's order, and the till takes the payment
area: integrations
topic: online-shops-and-orders
asks: Our reservations app seats a table and opens its order; guests order from a QR menu or a kiosk onto that order, and the till takes the payment
status: ready-with-limits
door: open-check
blocked-by: -
recipe: recipes/open_check.md
sample: samples/s55_front_of_house
request: -
verified: run by the product 2026-10-26 to 2026-10-28 (the door's first layer, through the API, 2026-10-26: an outside app's integration user opened a tab by its label and added to it, was refused a move and a close in the right's words, and read the check with no staff identity and no register; and POS train T19's walks on phone, counter and tablet: tables opened, two rounds added from two tills, the check claimed at Checkout and paid by card and cash, one line paid on each of two tills, Back giving the lines to the table, a pre-order tab paid, the close listing the open checks); and run by the kit sample S55 *Front of house* on our bench at POS train T19, 2026-10-29: its app's own user opened a seated party's table check from a reservation and a waiting party, a till added the dishes and took the payment; and by the kit sample S56 *Guest ordering* on the same bench, 2026-10-29: guests' orders from a table's QR code added to that table's one check, a kiosk order opened a tab, a till took the payment
related: own-online-shop
---
## What you build
An app that calls the *open check* door (`open_check/1`, POS version 2.1.0.667 and later) through `ivendnext_mpos.api.v1`: `floor_status` reads the store's tables, `check_open` opens a table's check (or a tab or pre-order by its label), `check_add_lines` adds what the guest ordered, and `check_preview` shows the shop's price of the open lines. The check holds what was ordered, never a price: the till prices it and takes the payment when the table pays. Every write carries a fresh random `key`; a retry sends the same key and the same request. The calls, rights and refusals are on the open check page (`contracts/pages/open_check.md`).

## Limits
- The retailer switches on **Table Service** on the POS Profile, sets up the floor (Floor Sections and Floor Places) in iVendNext Desk, and gives your app's user the store and one register there, first.
- Your app never pays, claims or prints a check: those calls are a till's only and refuse your app whatever it is granted.
- Ask only for *open a check*, *add to a check* and *see the checks*: sending to the kitchen, moving, merging, closing, voiding and comping are a person's decisions at the till.
- A line never carries a price, a discount or a server's note.
- Online only: a check needs a connection.
- A weighed line on an open check is refused at Pay until a later POS version.
- Which guest may see which check is your app's job: give each app its own user.

## Tell the customer
Your guests' orders reach the table's check on every till at once; staff send each round to the kitchen from a till, and the cashier takes the payment as for any sale, with every promotion and tax.
