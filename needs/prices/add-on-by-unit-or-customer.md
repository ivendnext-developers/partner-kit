---
id: add-on-by-unit-or-customer
title: A warranty or add-on that depends on the unit or the customer
area: prices
topic: fees-and-add-ons
asks: Offer a warranty or add-on that depends on the unit or the customer: a plan only for some models or serials, none for a customer who already holds one
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule_guard.md
sample: none
request: -
related: extended-warranty-as-item, offer-add-on-at-scan, warranty-check-at-till
verified: read from the product's code and contract pages 2026-11-04 · POS 2.1.0.681; nothing run for this card: the set-up it builds on was run for the card extended-warranty-as-item
---
## What you build
Four parts, each on a door that exists. Your service advises and checks; it never adds or prices a line, and it cannot change what the till offers: the cashier sees every add-on the retailer set up.
1. **The retailer sets up the add-ons**, as in the card *extended-warranty-as-item*: item options (POS 2.1.0, the *Item Options* switch on the POS Profile) or cross-sell rows on the item. iVendNext prices every add-on line.
2. **At the scan, say what suits this sale** (`recipes/capture.md`). A capture service on scan, filtered to the item groups, answers `notice`: *"This model qualifies for the 1- and 2-year plans."* It shows once the item and its choices are on the sale (with cross-sell rows, as the offer opens). Declare `allow_and_flag`: `refuse` would stop the unit being sold when your service is slow. Never use `confirm` for the plan: its *No* leaves the scanned item itself off the sale.
3. **Before payment, enforce it** (`recipes/rule_guard.md`). A check refuses a sale whose plan does not suit the unit or the customer, with the reason the cashier reads. It sees the customer and, when *Send each line's lot and serial number* is ticked on its subscription in Desk (a manifest cannot tick it), each line's serials. Check here, not at the scan: a barcode scan does not yet know the unit, and the scan sees the customer only if one is already on the sale.
4. **After the sale, follow the event feed** (`recipes/event_feed.md`): register the plan on `sale.booked`, and print a certificate number with *Fulfil at sale* (the card *voucher-at-payment*). Undo it on `return.booked` by reading the returned lines of the return the event names, and on `sale.cancelled` for the whole sale. A line voided on the till before payment books nothing and sends no event.

## Limits
- The check cannot pair a plan with its unit: its lines do not say which line an add-on rides, so with units of different eligibility in one sale it cannot tell which plan sits on which. Check the whole sale, not one pair.
- A sale with no customer gives a customer rule nothing to judge: have the check refuse with *"Pick the customer first"* where the rule needs one.
- On an order or a layaway plan the check runs once, at placement, and an order's lines carry no serial (the unit is picked at delivery). Delivery, instalments and pickup are not checked again.
- Slow, down or offline, a remote check is not asked: the till applies the down answer you declared (`allow_and_flag` books the sale and flags it in *Sales to review*; `refuse` stops it; `ask` asks the cashier). A certified sandboxed module check runs offline but never sees serials.
- One capture service answers scans for a POS Profile: another partner's scan notice, such as the kit's shelf-life sample (S23), cannot run at the same store. An item picked from a list is not asked.
- The notice is an 8-second toast that a later notice replaces, and the cashier can ignore it; only the check enforces.
- With item options a returned unit takes its plan with it unless the cashier unticks it, and a plan can come back alone; a cross-sell add-on returns on its own. Your records follow the return and cancel events.
- The limits of the cards *extended-warranty-as-item* and *offer-add-on-at-scan* apply: no serial-, batch-tracked or weighed add-on; several held sales whose option lines would merge are recalled one at a time; no add-on or required choice on an order for later; no cross-sell offer on an exchange's replacement.

## Tell the customer
While the till is online, the cashier is told which plans suit the item, and a plan the unit or the customer is not eligible for is refused before the customer pays. Your records of the plan follow the sale, the return and the cancel.
