---
id: offer-add-on-at-scan
title: An add-on offered when an item is scanned
area: prices
topic: fees-and-add-ons
asks: Offer an add-on when an item is scanned or suggest another item with it: gift wrap, a case with a phone, a warranty
status: ready-with-limits
door: configure
blocked-by: -
recipe: none
sample: none
request: -
related: extended-warranty-as-item, own-screen-in-shop-frame
verified: read from the product's notes 2026-10-27 · POS 2.1.0; nothing run for this card: the nearest is the card extended-warranty-as-item, whose set-up (one group of non-stock service items) was run on a sandbox
---
## What you build
Nothing of your own: the add-on is an ordinary item, and the till shows the choice itself when the main item is scanned. Two ways, both configuration (the card *extended-warranty-as-item* is the worked case, with its set-up steps and pricing):
- **Item options** (POS 2.1.0 on). An option group of add-on items, attached to the main item, with the item-options switch on in the store's POS Profile. The till opens a sheet before the line lands: pick none, one or several, and a group can be required.
- **The cross-sell suggestion** (every release). Rows on the main item naming the add-ons, without auto-add: the till offers them, and the cashier may skip. With auto-add the add-on lands without being asked.

Each add-on line is priced by iVendNext (the price list, or an amount the retailer set on the choice), taxed by its own tax template, voided with the main item and returned like any line.

## Limits
- An add-on item cannot be serial- or batch-tracked.
- With item options, a hold, a park to another till or a layaway park is refused when two option lines would merge on recall (offline, any park with an option line is refused); a required choice cannot go on an order for later or be an exchange's replacement; some of the sheet's sentences still say *dish*.
- With the cross-sell suggestion the cashier may skip the offer; a weighed or batch-tracked main item does not carry it.
- Do not rely on a promotion on an add-on item: the till keeps the add-on's own price on that line today (not run).
- A screen of your own for the choice is not needed, and not offered: the till draws these sheets itself (the card *own-screen-in-shop-frame*).

## Tell the customer
When the item is scanned the till offers its add-ons, such as gift wrap, a case or a warranty; the cashier picks, and each is its own line on the sale.
