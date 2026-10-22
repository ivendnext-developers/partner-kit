---
id: loyalty-provider
title: The customer's loyalty provider earned and spent at the till
area: customers
topic: loyalty-and-wallets
asks: Our loyalty provider's members earn on every sale and spend their balance at the till
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/loyalty_provider.md
sample: samples/s22_customer_loyalty
request: -
verified: read 2026-10-22 in the event feed, wallet and capture recipes and contracts · the three together not run (no sample calls a provider)
---
## What you build
Your outside app between the shop and the provider: earning from the event feed, spending through the wallet, and a one-time code where the provider asks for one. The provider's account and keys stay on your server.

## Limits
- The combination is not run: no sample calls a provider.
- A sale earns seconds after it books, not inside it.
- The wallet is online only: an offline till does not offer it.
- Going live needs a CERTIFIED conformance report: ask CitiXsys first (the wallet recipe, *Certification*).

## Tell the customer
Every booked sale of a member earns in your provider's programme, and members spend their balance at any till that is online.
