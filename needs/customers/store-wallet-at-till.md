---
id: store-wallet-at-till
title: A store wallet or a loyalty points balance spent at the till
area: customers
topic: loyalty-and-wallets
asks: Customers spend their cash back, store credit or loyalty points balance at the till
status: ready-with-limits
door: wallet
blocked-by: -
recipe: recipes/wallet.md
sample: samples/s22_customer_loyalty
request: -
verified: carried 2026-10-16 · not re-run
popular: yes
---
## What you build
Your service keeps the balance; the till asks it what this sale may use, takes it as a payment method, and gives it back to the same wallet on a return.

## Limits
- Online only: the wallet is never offered on an offline till.
- When your service is down, the till says it did not answer and the cashier takes another payment.

## Tell the customer
Customers pay with their balance at the till while it is online; a return gives the money back to the same wallet.
