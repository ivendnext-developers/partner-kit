---
id: sell-through-by-size-and-colour
title: Sell-through by size and colour, store by store
area: reports
topic: reports-and-bi
asks: Which sizes and colours of each style sell out and which sit, in each store, against the stock still there
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/shop_reports.md
sample: samples/s54_sell_through
request: -
verified: 2026-10-29 · laptop (51 tests, 46 of 46 canaries RED) · our test bench (the scenario 7/7, the least set of rights measured one at a time)
---
## What you build
A run as your manifest's own record type: an item group or one style in it, a start date, the size attribute and the colour attribute, and the stores. A Desk button on the run calls your service, which reads two of the retailer's own reports as your app's user with `run_report`, *POS Sale Report* (the till's units sold per item in each store, returns taken off) and *Stock Projected Quantity* (the stock per item in each store), and the items' attributes, and writes one row per style, colour, size and store: sold, in stock, the sell-through (sold divided by sold plus in stock) and *None left*. A Report Builder report lists the rows.

## Limits
- *Sold* is the till's sales (POS Invoice). Sales booked another way (an online store's orders, a Sales Invoice made in Desk) are not in it; a till order not yet delivered counts as sold while its unit is still in stock (what the report counts).
- *In stock* is today's, less any till sale whose stock has not left yet, so the figure reads from the start date up to today.
- The two reports belong to accounting and stock roles: the retailer adds your app's role to both (*Role Permission for Page and Report*) and gives it read or select on every record type their filters and lookups name (S54's README lists the nine). Read on POS Invoice and Select on Customer let your app's user read till sales and list customers; say so. The buyers' roles need Select on Item Attribute and Warehouse to fill a run. A new rights row comes with Read ticked: untick it where Select is enough.
- A press has 10 seconds: name fewer stores when the reports are slow, one style when a group has more rows than a run holds.

## Tell the customer
Each size and colour of each style, store by store: what sold since the date you choose, what is still in stock and the share sold, worked out from your own till sales and stock reports whenever a buyer presses the button.
