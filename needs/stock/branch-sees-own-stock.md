---
id: branch-sees-own-stock
title: A branch sees its own store's stock and the head office's
area: stock
topic: who-sees-stock
asks: A branch sees the stock of its own store and the head office's, no other
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: none
request: P-STORESCOPE
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 · a user with one warehouse permission: three lists and five report layouts fenced, three reports not; not run: two stores' permissions together, the till's stock panel, the other stock reports
---
## What you build
A User Permission on Warehouse for each store a user may see, their own and the head office's, set in iVendNext Desk.

## Limits
- With one permission, the Bin, Stock Ledger Entry and Warehouse lists, and the reports *Stock Balance* (also with another store chosen), *Stock Ageing* by store, *Stock Ledger*, *Total Stock Summary* and *Warehouse Wise Stock Balance*, showed that store only (run).
- Three reports showed other stores to the same user (run): *Item Balance (Simple)* and *Warehouse wise Item Balance Age and Value* showed every store, and *Stock Ageing* in its default layout showed the stock of every store, and of any store chosen in its filter. Test each stock report a branch may open, in each layout, and take away the ones that leak.
- A user with two permissions (own store and head office) was not run; nor were the other stock reports.
- At the till the *Other stores* stock panel shows every store or none, never own and head office (from the product's code, not run): ask for P-STORESCOPE.

## Tell the customer
A branch sees its own store's stock in the lists and in the reports we tested; some stock reports must be taken away from it, each one tested first, and the till's stock panel shows every store or none.
