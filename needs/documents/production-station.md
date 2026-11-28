---
id: production-station
title: Production station
area: documents
topic: own-records-and-fields
asks: A processing room's station that prints a priced tag in the week's colour with one tap, counts each worker's tags, and sends full carts into stock and on to stores
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/production_station.md
sample: samples/s64_production_station
request: -
verified: 2026-11-28 · bench (tags at two colours, one hundred printed in a row, decoded and scanned at the till; carts received at no value and moved to a store; the counts and sell-through)
---
## What you build
A station screen your service serves, opened by a signed link on the station's own browser: a worker taps their name, a category and one of its prices, and the page prints a tag whose barcode the engine made with the price inside, in the colour the rotation gives today's date. Each tag is a record of your own. *Cart full* posts, as your app's own user, a Material Receipt of the cart's tags into the processing room at no value and a Material Transfer of the same lines to a store, each once. A Desk button writes the production report: pieces by day, station and worker, and sell-through by colour week from the retailer's own POS Sale Report.

## Limits
- The station prints through the browser's own print: Chrome or Edge with `--kiosk-printing` prints each tag with no window; a tablet asks once a tag.
- A price is one of the prices the settings list for its category: one-off pieces are priced in the store.
- A site whose labels do not carry the price their scan reads back (before the engine's label fix of 12 October 2026) refuses the prices it cannot carry, and says so.
- A cart holds at most 5,000 tags; a report covers at most 92 days. Sold counts every unit of a colour's items in the week's window.
- Not in the sample, so each is a version of your own: a condition or grade on each piece, more than one level of category, raw printer commands through an agent on each station, the price tagged against the price sold.

## Tell the customer
Each worker prints a priced tag in this week's colour with one tap, and a full cart reaches the store's stock in one more; the lead sees who tagged how much, and what each colour sold.
