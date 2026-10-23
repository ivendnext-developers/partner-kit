---
id: sales-by-item-server-day-part
title: Sales by item, by who rang them and by the part of the day
area: reports
topic: reports-and-bi
asks: See what sold, who sold it and when in the day (breakfast, lunch, dinner) across stores
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/restaurant_back_office.md
sample: samples/s45_restaurant_back_office
request: -
verified: 2026-10-23 · bench
related: recipes-off-stock, food-cost-by-recipe
---
## What you build
Your service keeps each sale's lines on its own records as it takes the sales up (the item, quantity, amount net of tax, the user who rang it, the time and the retailer's name for that part of the day), and your manifest's report lists them with totals, to filter and group in Desk.

## Limits
- A sale shows in the report once it has been taken up by a press.
- *Who sold it* is the till user who rang the sale.

## Tell the customer
One report of sales by item, by who rang them and by breakfast, lunch or dinner, across your stores.
