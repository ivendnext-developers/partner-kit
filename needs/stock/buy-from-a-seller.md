---
id: buy-from-a-seller
title: Buying pieces outright from a seller for cash or store credit
area: stock
topic: moves-and-orders
asks: A person brings pieces to the counter and the store buys them there and then, paying in cash or in store credit, and the pieces go into stock at what was paid
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/consignment_payouts.md
sample: samples/s61_consignment_payouts
request: -
related: store-wallet-at-till, consignment-payouts, donation-intake
verified: read against the kit's samples S45, S57, S61 and the wallet recipe 2026-11-09 · not run
---
## What you build
A purchase as your manifest's own record type, shaped as S57's donation and S61's payout: the seller (a customer; for cash alone a name typed at the counter), the store, the day, and one row per lot with its item and what was paid, *Cash* or *Store credit*. A Desk button calls your service, which makes and submits the Stock Entry of type Material Receipt at the price paid, as S45's service makes its Material Issue (`role_rights` read, create and submit on Stock Entry), and for *Store credit* adds the amount to the customer's balance in the wallet your service keeps (`recipes/wallet.md`). A save rule locks the purchase once it is booked.

## Limits
- Each row names one of the retailer's items (a generic item for each kind of goods), or your service makes the item first (create on Item in `role_rights`).
- Store credit needs the seller to be a customer, since the wallet is spent only with a customer on the sale; a seller typed in is paid in cash, or added as a customer first.
- The Material Receipt books the stock against the company's stock adjustment account: the cash paid and the credit owed are your service's own entries (the credit as a liability, the wallet's account), or the books show a gain and a cost.
- Store credit is spent at the till through the wallet (the card *store-wallet-at-till*): online only, and a wallet that goes live passes the certification in `recipes/wallet.md`. A store that pays only cash leaves the wallet out.
- Not run: no sample buys from a seller yet.

## Tell the customer
Each purchase is recorded at the counter with who sold what and what was paid, the pieces go into stock at that price, and credit is added to a customer's balance when they choose it over cash.
