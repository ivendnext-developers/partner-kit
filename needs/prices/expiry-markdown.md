---
id: expiry-markdown
title: A markdown on stock as its expiry date nears
area: prices
topic: price-lists
asks: Mark down perishable stock automatically as its expiry date nears, by our own steps, so it sells before we throw it away
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/expiry_markdown.md
sample: samples/s38_expiry_markdown
request: -
verified: 2026-10-22 · bench
---
## What you build
Markdown steps on each perishable item group (25% off from 5 days before expiry, 50% off from 2 days), and a **Mark down** button on the Batch list. A manager ticks the lots expiring this week and presses it: your service writes each lot's own price on the shop's selling price list, valid until the lot's expiry date, and changes it when the lot reaches its last step. The till already rings a lot at its own price and prints its lot label.

## Limits
- A manager presses it, once a day: there is no run without a press.
- Lot-tracked items only: an item with no lots has no expiry date.
- While any lot on the site has a price of its own, the tills do not sell a lot-tracked item offline; each press removes up to 20 of the app's expired ones (a lot price you typed yourself stays until you delete it).
- Before a line is priced, the item's tile or a scan can show another lot's price; the line and the receipt carry the right one.
- A customer with their own price for the item pays it on a scanned lot, not the markdown.
- An item's own barcode rings the lot the shop picks (Stock Settings); a scanned lot label rings that lot.
- One set of steps per item group, one price list per site, rounded down to the currency's smallest unit.
- A price the shop typed for a lot is never changed.
- A new item price takes the markdown off a scanned lot label until the next press.
- Up to 100 lots a press, and as many as the service writes in 6 seconds; press again for the rest.

## Tell the customer
Each morning your manager presses one button, and the lots near their expiry date sell at your own markdown until they expire; the cashier does nothing new.
