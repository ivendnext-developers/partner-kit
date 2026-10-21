---
id: question-on-quantity-change
title: A question when the quantity of a line changes
area: till
topic: questions-during-the-sale
asks: A question when the quantity of a line changes, before Pay
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/capture.md
sample: samples/s20_capture
request: -
verified: run by the product 2026-10-18 (POS train T12's walk, counter, phone and tablet frames: a repeat scan, ＋ in the line sheet and the variant card's Add each asked once; allowed, confirmed and refused back to the last allowed quantity); not run by a kit sample on a sandbox
---
## What you build
A capture service on the quantity-change event (`qty_change`), from POS build 2.0.0.654: when a line your filter names changes quantity, the till sends its last allowed quantity and the new one, and your service answers allow, confirm, refuse or a notice (`recipes/capture.md`, step 5c). Sample S20 adds a count on one line: up to three allowed, four or five asked about, more refused.

## Limits
- Serial- and lot-tracked lines are outside it, as are a return's quantities and an order's change; a weighed line, a set, a gift card and an offer's companion item are never asked.
- A held, parked or converted sale comes back rebuilt: each line starts at the quantity it arrives with. Hold and Park ask first, so a refused quantity does not come back that way.
- A refusal or a *No* puts back the last allowed quantity. A burst of presses is asked once, 600 ms after the last.
- Offline, or when your answer never comes, the declared down answer applies; with `allow_and_flag` the change is flagged only when the sale is paid online or synced.
- It shapes the cashier's flow; a rule that must hold when the sale is booked is a check before payment (the card *line-quantity-cap*).

## Tell the customer
The till asks our service when the quantity of a named item changes, before Pay, and puts back the last allowed quantity on a refusal; serial- and lot-tracked items, returns and orders are not asked.
