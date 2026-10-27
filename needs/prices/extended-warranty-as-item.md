---
id: extended-warranty-as-item
title: An extended warranty chosen when a product is sold
area: prices
topic: fees-and-add-ons
asks: Three extended warranties (1, 2 or 3 years, each at its own price) to choose from when a laptop is scanned; sell an extended warranty with a product
status: ready-with-limits
door: configure
blocked-by: -
recipe: none
sample: none
request: -
verified: run on a sandbox 2026-10-27 · POS 2.1.0.666, the set-up only: an option group saved and compiled onto the laptop's rows (System Generated choices with no amount, Amount choices at their amounts), the profile switch turned on and back off, every write undone; the sale on the till, the limits and the cross-sell way read from the product's notes, not run
---
## What you build
Nothing of your own: the warranty is an item, and the till offers it when the product is scanned. Two ways, both configuration. The warranty line is priced by iVendNext (the price list, or the amount the retailer set), never by a partner; taxed by its own tax template; voided with the laptop; returned like any line.
- **Item options** (POS 2.1.0 on). One non-stock service item per term, and one option group *Extended warranty*: pick up to 1, or required with a *No extended warranty* choice at 0 so the cashier must ask (a zero line on the sale; not run). Attach the group to the laptops and switch item options on in the store's POS Profile (off by default). The cashier scans the laptop, picks a term on the till's sheet and carries on.
- **The cross-sell suggestion** (every release). Put the warranty items as rows on the laptop item, without auto-add: the till offers them on the scan.

**Pricing, one of two.** Each warranty's price on the price list (one price for every laptop; price type *System Generated*), or a fixed amount on each choice (price type *Amount*) when the price depends on the laptop, with one group per laptop price band.

**What a partner adds, from doors that exist:** registering the warranty with its provider after the sale (an outside app on the event feed, `recipes/event_feed.md`); a warranty look-up during the sale (the card *warranty-check-at-till*); a certificate number printed under the warranty line (*Fulfil at sale*, chapter 9); prices kept in step from a provider (an outside app writing the items' prices over the API).

## Limits
- The warranty items cannot be serial- or batch-tracked.
- With item options, a hold, a park to another till or a layaway park is refused when two option lines would merge on recall, such as the same warranty at the same price on two laptops (offline, any park with an option line is refused); the cashier pays the sale now.
- With item options, a required choice cannot go on an order for later or be an exchange's replacement. Some of the sheet's sentences still say *dish*.
- With the cross-sell suggestion the cashier may skip the offer, or pick more than one warranty; a weighed or batch-tracked laptop does not carry it (a serial-tracked one does).
- A warranty with a certificate number (*Fulfil at sale*) cannot be sold offline, and its refund waits until the code is cancelled with the provider.
- Do not rely on a promotion on a warranty item: the till keeps the warranty's own price on that line today (not run).

## Tell the customer
The cashier is offered the warranty terms when the laptop is scanned and picks one; it is its own line on the sale, priced and taxed like any item.
