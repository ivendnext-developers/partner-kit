---
id: products-on-promotion-filter
title: Filter the product list to products on promotion
area: prices
topic: promotions
asks: Filter the product list to the products on promotion
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-10-16 · not re-run; the outside app is not built or run
---
## What you build
A check field of your own on the item, kept current by an outside app that reads the active promotions; the Desk list filters on it, and a saved view or a report shows it.

## Limits
- The flag lags a promotion's start and end by the app's schedule.
- On the till a field rule can show the flag, within the three more item fields it allows.
- A coloured row in the Desk list has no door today (the card products-on-promotion-colour).

## Tell the customer
The product list filters to what is on promotion, updated each time our app runs.
