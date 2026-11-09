---
id: buy-from-a-seller
title: Buying pieces outright from a seller for cash or store credit
area: stock
topic: moves-and-orders
asks: A person brings pieces to the counter and the store buys them there and then, paying in cash or in store credit, and the pieces go into stock at what was paid
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/donation_intake.md
sample: samples/s57_donation_intake
request: -
related: store-wallet-at-till, consignment-payouts, donation-intake
verified: 2026-11-09 · read against the kit's samples S57, S61 and the wallet recipe; the build itself not run
---
## What you build
A purchase as your manifest's own record type: the seller (a customer, or a name typed at the counter), the store, the day, and one row per piece or lot with what was paid, and *Cash* or *Store credit*. A Desk button calls your service, which makes the Stock Entry of type Material Receipt that takes the pieces into stock at the price paid (the way S57's goods are taken in), and for *Store credit* adds the amount to the seller's balance in the wallet your service keeps (`recipes/wallet.md`). A save rule locks the purchase once it is booked.

## Limits
- The cash handed over is the store's own entry in its cash book: your version records it, or a person does.
- The store credit is spent at the till through the wallet, which is online only (the card *store-wallet-at-till*).
- A higher credit than cash offer is a field on the purchase or a setting your service reads.
- Whatever the store must keep about the seller where a local rule asks it, an ID or a signed receipt, is a field or a print of your own.
- Not run: no sample buys from a seller yet.

## Tell the customer
Each purchase is recorded at the counter with who sold what and what was paid, the pieces go into stock at that price, and credit is added to the seller's balance when they choose it over cash.
