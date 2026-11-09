---
id: delivery-orders-age-checked-at-the-door
title: Alcohol orders from DoorDash, Uber Eats, Instacart and Gopuff, age checked at the door
area: integrations
topic: online-shops-and-orders
asks: Alcohol orders from the delivery apps come into the store's books, and we know the courier checked ID at the door
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
related: delivery-marketplaces-through-a-delivery-partner, check-before-document-submit, extra-fields-on-shop-documents
verified: carried 2026-11-09 from the marketplaces' published help pages · not run against any marketplace
---
## What you build
The route of the card *delivery-marketplaces-through-a-delivery-partner*: a service of yours (or the delivery partner's) turns each order into a Sales Order; no kitchen ticket is needed. When the courier takes the order it makes the Delivery Note (or a Sales Invoice that updates stock). Add one field of your own on Sales Order (the card *extra-fields-on-shop-documents*) for the marketplace's word that the courier checked ID, and write it when the marketplace sends one.

## Limits
- A Sales Order moves no stock. Until the Delivery Note or invoice exists the bottle is still in stock, and the register book and excise return, which read stock movements, do not have it.
- The age is checked at the door by the marketplace's courier, in the marketplace's own app: DoorDash, Instacart and Gopuff say so on their help pages (Uber Eats' not read). iVendNext is not in that step and holds no record of it unless your service writes one.
- The till's age check runs only at the till's own Pay, so it never sees these orders. A document check on Sales Order is the door for a rule of your own (the card *check-before-document-submit*).
- A marketplace may send no word that the check was done: the field then stays empty. Do not show it as a check iVendNext made.
- An order refused at the door (no valid ID) comes back to the store: a credit note puts the bottle back if it was invoiced, and an order not yet delivered is closed. Read the marketplace's terms for whether the customer is charged. Not run.
- Each marketplace decides whether a store may sell alcohol on it, and Instacart's guide puts last-mile compliance on the retailer. The delivery card names Otter, Deliverect, Chowly and Olo; whether one carries alcohol for each marketplace is not read: ask each.
- No delivery partner is connected to iVendNext today. Every limit of the delivery card applies: cancels, repeated orders, sold-out items, settlement.

## Tell the customer
Marketplace alcohol orders reach the store's books as Sales Orders and leave stock when the courier takes them, once your delivery link is built. The courier checks ID at the door in the marketplace's app; iVendNext does not repeat that check, and no link is connected yet.
