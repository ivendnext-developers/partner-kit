---
id: recipes-off-stock
title: A dish's recipe takes its ingredients off stock after the sale
area: stock
topic: moves-and-orders
asks: Sell a dish at the till and have its ingredients (the bun, the patty, the coffee beans, the milk) come off the kitchen's stock by its recipe, without counting each one by hand
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/restaurant_back_office.md
sample: samples/s45_restaurant_back_office
request: -
verified: 2026-10-23 · bench
related: food-cost-by-recipe, sales-by-item-server-day-part, allergens-on-till-and-receipt
---
## What you build
Each dish is a plain item that is not stocked, with the retailer's own recipe on it (a bill of materials: the parts and how much of each makes one dish; a recipe may hold another, such as a sauce). An **Issue ingredients** button on your settings record calls your service, which reads the till sales no issue has taken up yet, opens each dish's recipe into the stock items it uses, and books the retailer's own Material Issue of those parts: one per store and day, safe to press again, a sale never taken twice, a sale made offline and posted late caught by the next press.

## Limits
- The ingredients come off when someone presses the button (after the day's close, say), not at the moment of the sale.
- When the store is short of a part, nothing of that store-day is taken off and the issue names every short part; the next press after a delivery or a count books it.
- A sale older than the press's look-back (7 days by default) is never taken up.
- An ingredient counted in whole units (a bun) takes whole quantities: a recipe that uses half of one is refused by iVendNext and named on the issue.

## Tell the customer
Ring the dish as today: the recipe takes its ingredients off the kitchen's stock with one press a day, and a short ingredient is named rather than booked below zero.
