---
id: click-and-collect-board
title: A store's list of web orders to pick and hand over
area: integrations
topic: online-shops-and-orders
asks: Click and collect — the store sees which web orders to pick and which customers are coming to collect
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/click_and_collect.md
sample: samples/s33_click_and_collect
request: -
verified: 2026-10-18 · bench
---
## What you build
A manifest: a Report Builder report of the web orders still to pick, two fields on the delivery note that can be set after it is submitted, *Handed over* (a list column and filter: the Delivery Note list filtered on Status To Bill or Completed, Is Return No, % Returned less than 100, Handed over No, Customer's Purchase Order No set, the store's warehouse and a date on or after the install is the waiting list) and *Collected by*, and a workspace that opens both. A web order is an order with the web shop's order number. Nothing leaves the shop.

## Limits
- The lists are in Desk. The till's own pickup board lists till sales only, and a page on the till opens only over a sale.
- Who handed an order over, and when, is the delivery note's own history, not a field.
- The waiting list is a filtered list, not a report: a report cannot use a field its own manifest adds.
- An order returned before collection stays on the list (a return does not yet update its original): cancel its note instead.
- Notes from before the install would wait too: add a date to the saved filter. A return or an amended note copies the two fields.
- A Desk order typed with a customer's order number, or a web order shipped from the store, shows too.
- A web order booked as a sales invoice shows only once its delivery note exists.

## Tell the customer
Each store gets a Desk board of the web orders to pick and the customers coming to collect, and records each hand-over on the delivery note.
