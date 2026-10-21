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
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 · a user with one warehouse permission: three lists and five report layouts fenced, three reports not; the till's store list run by the product 2026-10-16 (phone, counter and tablet: the item card, the Other stores panel and the order's store list narrowed); not run: two stores' permissions together, the other stock reports
---
## What you build
In iVendNext Desk, a User Permission on Warehouse for each store a user may see, their own and the head office's. For the till, from POS build 2.0.0.654, list the stores on the till's POS Profile, in *Stores this till may see* (`recipes/configure_no_code.md`).

## Limits
- With one permission, the Bin, Stock Ledger Entry and Warehouse lists, and the reports *Stock Balance* (also with another store chosen), *Stock Ageing* by store, *Stock Ledger*, *Total Stock Summary* and *Warehouse Wise Stock Balance*, showed that store only (run).
- Three reports showed other stores to the same user (run): *Item Balance (Simple)* and *Warehouse wise Item Balance Age and Value* showed every store, and *Stock Ageing* in its default layout showed the stock of every store, and of any store chosen in its filter. Test each stock report a branch may open, in each layout, and take away the ones that leak.
- A user with two permissions (own store and head office) was not run; nor were the other stock reports.
- At the till, with a list: the *Other stores* panel and a cross-store order's store list show the listed stores only, and the item card the listed stores and the till's own; a head office that is not a retail store shows in the item card only. An order to a store not listed is refused.
- Without a list, and before build 2.0.0.654: the panel shows every store marked a retail store, or none, and the item card every warehouse.
- The list narrows stock and orders, not sales: finding another store's sale for a return, or recalling a held sale, reaches every retail store.

## Tell the customer
A branch sees its own store's stock in the lists and in the reports we tested; some stock reports must be taken away from it, each one tested first, and the till shows the stores its POS Profile lists.
