---
id: click-and-collect-board
title: A store's list of web orders to pick and hand over
area: integrations
topic: online-shops-and-orders
asks: Click and collect — the store sees which web orders to pick and which customers are coming to collect, on arrival, and the orders a passenger never collects (no-show recovery)
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/click_and_collect.md
sample: samples/s33_click_and_collect
request: -
verified: 2026-10-18 · bench; arrival and no-show limits added 2026-11-22, not run
---
## What you build
A manifest: a Report Builder report of the web orders still to pick, two fields on the delivery note that can be set after it is submitted, *Handed over* (a list column and filter: the Delivery Note list filtered on Status To Bill or Completed, Is Return No, % Returned less than 100, Handed over No, Customer's Purchase Order No set, the store's warehouse and a date on or after the install is the waiting list) and *Collected by*, and a workspace that opens both. A web order is an order with the web store's order number. Nothing leaves the retailer's iVendNext.

## Limits
- The lists are in Desk. From POS version 2.1.0 the workspace is never in the Desk's menu: the retailer's administrator opens it from the App library, and store staff find it with the search bar. The till's own pickup board lists till sales only, and a page on the till opens only over a sale.
- Who handed an order over, and when, is the delivery note's own history, not a field.
- The waiting list is a filtered list, not a report: a report cannot use a field its own manifest adds.
- An order returned before collection stays on the list (a return does not yet update its original): cancel its note instead.
- Notes from before the install would wait too: add a date to the saved filter. A return or an amended note copies the two fields.
- A Desk order typed with a customer's order number, or a web order shipped from the store, shows too.
- A web order booked as a sales invoice shows only once its delivery note exists.
- A passenger collecting on arrival is a customer collecting: the board knows no flight or arrival time. A field for them is a field of your own on the delivery note, not run.
- An order nobody collects (a no-show) stays on the list until it is dealt with: cancel its note, then close its sales order, or it goes back on the list of orders to pick; a note already billed needs its invoice cancelled first. A job of yours that lists the old ones, or a person, does it. What happens to money paid on the web is the web store's: read its terms. Not run.

## Tell the customer
Each store gets a Desk board of the web orders to pick and the customers coming to collect, and records each hand-over on the delivery note. It knows no flight, and an order nobody collects is cancelled by a job of yours or by a person.
