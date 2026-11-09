---
id: wine-club-shipments-and-allocations
title: A wine club's releases, members' allocations and shipments
area: customers
topic: loyalty-and-wallets
asks: Club members each get their allocation of a release, the orders are made and shipped to them at the club price, and nobody is sent twice
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/desk_action.md
sample: samples/s61_consignment_payouts
request: -
related: member-price-by-tier, consignment-payouts, own-online-shop
verified: carried 2026-11-09 from the kit's pages and S61 · not run
---
## What you build
A member and a release as your manifest's own record types: a member names a Customer; a release lists each member's allocation of each wine. A Desk button on the release calls your service, which answers at once and then makes one Sales Order per member, at the club's price list (*selling_price_list*), with the release's name in *po_no*. It looks each order up by customer and *po_no* and works on the button's *idempotency_key*, so a second press makes none that exists. The same shape as S61, which never pays a line twice. Your service or the carrier's own system prints the label and takes the shipment.

## Limits
- The club price at the till is configuration (the card *member-price-by-tier*). Name the same price list on each order, or the member sees two prices.
- A Desk button's service has 3 seconds to answer, 10 at most, and a retry is not made for it: a large club's orders are made after the answer, and the release shows what is done.
- An allocation is a count of your own. Sales Order has a *reserve stock* field; whether it holds stock back for a member is not run, so check it on a sandbox before you promise it.
- Where a store may ship wine to a member, and the carrier's adult signature, are the customer's and the carrier's to settle. The card names no state's rule. Sales tax on a shipment to another state is the customer's to settle.
- The kit has no stored-card door: a card kept on file and a charge each release are the payment provider's own tool.

## Tell the customer
Each release is allocated to the members, and the orders are made at the club price from one press; the shipping label and the member's card charge are your link's work.
