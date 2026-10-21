---
id: count-list-totals
title: The list of stock counts with quantity, difference and stock value
area: stock
topic: counts
asks: The list of stock counts showing the quantity, the difference and the stock value
status: ready-with-limits
door: manifest
blocked-by: -
recipe: guide/07_manifests.md
sample: none
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 and 2.0.0.645 · the count's header holds one amount; the manifest report with item-row columns run by the product 2026-10-18 (POS train T12's walk: exactly its columns, one line per row); not run: a total of the rows on a count, by a kit sample
---
## What you build
From POS build 2.0.0.654, a manifest report on the stock count, *Count lines*, with columns from its item rows: `posting_date`, `items.item_code`, `items.qty`, `items.quantity_difference`, `items.amount_difference`, and a totals row (`guide/07_manifests.md`, *A report's columns from one table of the record*). A header total of the rows is a save rule of kind `derived`, formula `sum_rows`, into a field of your own (`recipes/save_rules.md`).

## Limits
- One table per report, one line per item row; with a totals row, no number column of the count itself.
- *Quantity Difference* is a read-only field, so its total stays blank in the totals row (run by the product).
- Desk opens the report sorted by the record type's default, not by the report's own order.
- A filter on the item rows leaves out a count with no rows.
- A `sum_rows` total is a figure on screen, never money; a row saved on its own re-totals at the count's next save.
- Before build 2.0.0.654 a manifest report took plain field names only, and a save rule could not total rows.

## Tell the customer
A *Count lines* report lists every counted item with its quantity and differences, with a totals row; a figure Desk shows read-only, such as the quantity difference, is not totalled.
