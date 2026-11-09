---
id: value-recovered-from-donations
title: What the donated goods sold for, store by store
area: reports
topic: reports-and-bi
asks: For each store and period, the donations taken in and what the item group the donated goods are sorted into sold for, so the chain sees which stores recover the most from what is given
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/shop_reports.md
sample: samples/s54_sell_through
request: -
related: donation-intake, sell-through-by-size-and-colour
verified: read against the kit's samples S54 and S57 2026-11-09 · not run
---
## What you build
A run as your manifest's own record type: the stores, a start date and the item group the retailer sorts donated goods into. A Desk button on the run calls your service, which reads the till's *POS Sale Report* per store with `run_report`, as S54 does (net sales, filtered by item group), the deliveries made against orders, taken off as S54 takes them off, and the donations (S57's record) each store took in since the date. It writes one row per store: the donations, the goods counted by the unit each was given in (items, bags, boxes), and the group's sales. A Report Builder report lists the rows.

## Limits
- The figure is the item group's sales, set beside the donations of the same store and period: sales are not traced from a donation to its sale, and pieces bought from sellers or consigned that sit in the group count too. Tracing one needs a donation's goods to go into stock under their own item, batch or serial number.
- Neither the donor receipt nor this report puts a value on a donation: a valuation for a donor's tax claim is a version of your own.
- Sales booked another way than the till (a Sales Invoice made in Desk) are not in the report.
- A press has 10 seconds and S54 takes at most 20 stores a run. The retailer adds your app's role to *POS Sale Report* and gives it read on *PP DON Donation* (`role_rights`), as on the card *sell-through-by-size-and-colour*.
- Not run: no sample adds up donations against sales yet.

## Tell the customer
For each store, the donations taken in and what the item group of donated goods sold for since the date you choose, worked out from your own till sales whenever a buyer presses the button.
