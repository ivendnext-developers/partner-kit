---
id: distributor-ordering-and-invoices
title: Ordering from our distributors, their price books, and paying their invoices
area: stock
topic: moves-and-orders
asks: Each distributor's price book and order sheet in our system, orders sent to them from what the stores need, and their invoices matched and paid
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
related: low-stock-reminder, derived-price-list, edi-with-a-us-trading-partner
verified: carried 2026-11-09 from the kit's pages and the record types · not run against a distributor or an ordering platform
---
## What you build
Your outside app between a distributor (or a distributor ordering platform such as Provi) and iVendNext, on the API and the event feed. It writes each distributor's price book as Item Price rows on a buying price list, turns the stores' reorder requests (the card *low-stock-reminder*) into a Purchase Order, and sends it on in the distributor's format. The delivery is entered as a Purchase Receipt, where stock enters, and the invoice as a Purchase Invoice with the distributor's number in its *bill_no*. When the money is sent, your service writes the Payment Entry. S34 shows a hold on a purchase order for a rule of your own.

## Limits
- A distributor's price goes on the draft Purchase Order, where staff see it before they submit; it is never changed after. A different price on the invoice is the invoice's own.
- A price book comes as the distributor sends it: a case or a bottle, a deposit and a state's fees need their own rows, and a price valid for a month needs your service to change it on the day.
- A short or broken delivery is entered as received: the receipt, not the order, is what stock sees.
- No ordering platform or distributor is connected to iVendNext today, and no platform's published interface was read for this card. Each one's access is yours or the customer's to get.
- iVendNext moves no money to a distributor: the transfer is the bank's or the platform's, and your service records it afterwards.
- A state may set the terms a distributor can give a retailer. The card names none: the customer reads its own state's rules.
- The feed reports a saved order or invoice after the fact.

## Tell the customer
Your distributors' prices sit on a buying price list, and each store's reorder becomes a purchase order sent through your link; the delivery, the invoice and your payment are recorded against it. No distributor or ordering platform is connected yet.
