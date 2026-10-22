---
id: recall-and-disposal
title: A recall by batch, traced to stores and customers, and disposal on the record
area: stock
topic: batches-and-expiry
asks: Block a recalled batch at every till and store at once, find its stock and the customers it reached, dispose of it with the regulator's visit recorded, and refuse short-dated deliveries
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/expiry_recall.md
sample: samples/s40_expiry_recall
request: -
verified: 2026-10-22 · bench
related: minimum-shelf-life-at-receipt, expiry-alert-before-date, expiry-markdown
---
## What you build
A recall notice with a **Block these batches** button: your service switches the lots off (the till's automatic lot read drops them at once), reads the stock ledger for each store's stock and the sales that reached customers, and writes both onto the notice with a progress record per store. A **Disposal Record** carries the regulator's visit and locks once it is recorded; a document check on Stock Entry refuses a controlled disposal without it. A document check on Purchase Receipt refuses short-dated lots unless the line carries a Letter of Undertaking with its days, and flags the ERP's own receipts instead. An **Expiry Worklist** with a **Refresh** button lists the lots near expiry per store.

## Limits
- A Desk delivery or invoice naming a blocked lot by hand still submits until the POS app refuses disabled lots on every stock document.
- An offline till keeps a blocked lot until it syncs; press again after the sync to trace its sales.
- A lot with no expiry date is never blocked by the app (saving it would write a guessed date): enter the pack's date first.
- While the service is down, receipts, stock entries and stock counts wait: all three checks refuse (their declared answer).
- A schedule set only on an item group is not read for the disposal rule.
- Up to 100 lots a notice.

## Tell the customer
When the regulator recalls a batch, one press stops it at every online till, tells each store how much it holds and, at consumer depth, lists the sales that reached customers (walk-in sales under the walk-in customer); controlled stock leaves for destruction only with the inspector's visit on record, and a short-dated delivery is refused at the Desk's goods-in (an ERP's is flagged).
