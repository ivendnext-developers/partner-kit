---
id: liquor-excise-returns
title: Liquor excise returns
area: documents
topic: own-records-and-fields
asks: A liquor store's excise return figures, volume and pure alcohol per duty class, per store and period, from its own stock, kept as filed
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/liquor_excise_returns.md
sample: samples/s62_liquor_excise_returns
request: -
verified: 2026-10-31 · bench
---
## What you build
A duty class as your manifest's own record type, and three fields on Item: the item's class, its millilitres per stock unit and its strength. A return per store and period with a Desk button whose service reads the store's own stock ledger with the list API's sums: each item's balance at both ends of the period, and the period's movements by kind. It writes twelve lines per duty class, from the opening stock through what came in, what went out and what counts changed to the closing stock, each in units, volume and pure alcohol. A workflow step the Stock Manager takes files it, and a save rule then keeps its figures as filed.

## Limits
- The figures are the books as they stand when the return is worked out; a late till sync or a back-dated entry changes the next return's opening, never a filed one.
- One store and one period a press; a store with very many items and long history can run out of the press's time.
- The authority's own form, codes, duty rates and an electronic filing are a version of your own, built on these figures.

## Tell the customer
Your excise return's volumes and pure alcohol per duty class come from your own stock, split the way the authority asks, and stay as you filed them.
