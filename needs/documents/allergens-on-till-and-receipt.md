---
id: allergens-on-till-and-receipt
title: Allergens on the till's line and the receipt, checked against the recipe
area: documents
topic: receipts
asks: Show a dish's allergens to the cashier on the sale and print them on the receipt, and make sure the dish lists every allergen its ingredients carry
status: ready-with-limits
door: field-rules
blocked-by: -
recipe: recipes/restaurant_back_office.md
sample: samples/s45_restaurant_back_office
request: -
verified: 2026-10-23 · bench
related: recipes-off-stock, item-fields-on-receipt
---
## What you build
An *Allergens* field on Item from your manifest, filled by the shop on its dishes and ingredients in its own words. Two field rules on the till theme (POS Studio, *Fields*) show it under each line of the sale and print it under the item on the receipt. A **Check allergens** button on the Item list names any dish that leaves out an allergen one of its recipe's ingredients carries, and any word that is not on the shop's allergen list.

## Limits
- The check names what to fix and changes nothing: the shop corrects the dish.
- The kitchen ticket does not print it yet.
- The till shows at most three extra item fields per theme.

## Tell the customer
The cashier sees a dish's allergens on the sale, the receipt prints them, and one press checks every dish against its recipe.
