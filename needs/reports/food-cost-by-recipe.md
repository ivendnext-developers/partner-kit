---
id: food-cost-by-recipe
title: Food cost by recipe against actual, from the retailer's own stock
area: reports
topic: reports-and-bi
asks: Show what the food should have cost by the recipes against what it really cost after waste and the stock count, as a percentage of sales
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/restaurant_back_office.md
sample: samples/s45_restaurant_back_office
request: -
verified: 2026-10-23 · bench
related: recipes-off-stock, sales-by-item-server-day-part
---
## What you build
A food cost record (a store and a period) with a **Work out food cost** button: your service reads the retailer's stock ledger for that store and period and writes, per ingredient, what the recipes used, what was sold as it is, what other issues took (waste, staff meals) and what the count found missing, with the cost by recipe, the actual cost and both as a percentage of the period's sales.

## Limits
- The actual cost is only as true as the stock count at the period's end: count first.
- Receipts and transfers between stores are not use and are left out.

## Tell the customer
One press gives the period's food cost by recipe and in fact, and the ingredients where the two differ.
