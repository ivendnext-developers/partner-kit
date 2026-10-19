---
id: count-list-totals
title: The list of stock counts with quantity, difference and stock value
area: stock
topic: counts
asks: The list of stock counts showing the quantity, the difference and the stock value
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/manifest.md
sample: none
request: P-RULES3, P-REPORTCOLS
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 and 2.0.0.645 · the count's header holds one amount; Desk's report view accepted item-row columns (no counts on the site, so no rows were seen; a sum grouped by document was refused); not run: a saved report with rows, the outside app that fills totals
---
## What you build
The difference is a column of the list, by configuration. Totals of the item rows are a prefixed field on the document, filled by an outside app after each save, or a report the user builds in Desk.

## Limits
- The header holds the difference amount only; quantity and stock value are on the item rows (read on a sandbox).
- A save rule cannot sum the rows (a rule never writes quantity or money): ask for P-RULES3.
- A manifest cannot declare a report with columns from the item rows (its checker takes plain field names); Desk's report view accepted them, but a sum grouped by document was refused and no rows were seen: test it on the customer's data, and ask for P-REPORTCOLS.
- Totals appear after the save, not while the user types.

## Tell the customer
The count list shows the difference as it stands; totals of quantity and value appear a moment after each save, or, once tested on your data, in a report in Desk.
