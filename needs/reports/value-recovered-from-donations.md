---
id: value-recovered-from-donations
title: What donated goods earned, store by store
area: reports
topic: reports-and-bi
asks: For each store and period, the donations taken in and what the donated goods sold for, so the chain sees which stores recover the most from what is given
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/shop_reports.md
sample: samples/s54_sell_through
request: -
related: donation-intake, sell-through-by-size-and-colour
verified: 2026-11-09 · read against the kit's samples S54 and S57; the build itself not run
---
## What you build
A run as your manifest's own record type: the stores, a start date and the item group the retailer sorts donated goods into. A Desk button on the run calls your service, which reads the donations (S57's record) taken in at each store since the date, and the till's sales per item and store with `run_report` as S54 does, and writes one row per store: donations taken in, pieces, what the item group sold for, and what is still in stock. A Report Builder report lists the rows.

## Limits
- The sales are those of the item group, set beside the donations of the same store and period: they are not traced from a donation to its sale. Tracing one needs a donation's goods to go into stock under their own item, batch or serial number.
- The donor receipt states no value, and so does this report: a valuation for a donor's tax claim is a version of your own.
- Sales booked another way than the till (a Sales Invoice made in Desk) are not in the till's report; the card *sell-through-by-size-and-colour* has the same limit.
- Not run: no sample adds up donations against sales yet.

## Tell the customer
For each store, what came in as donations and what the donated goods sold for since the date you choose, worked out from your own till sales whenever a buyer presses the button.
