---
id: gift-card-on-spend
title: A gift card for a big spend
area: customers
topic: loyalty-and-wallets
asks: A gift card for a spend over a threshold, spendable after a hold
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/gift_card_on_spend.md
sample: samples/s25_gift_on_spend
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
An outside app reads booked sales from the feed and issues the retailer's own gift card, released after the hold.

## Limits
- The card is made after the sale, not on its receipt.
- A return without the receipt names no sale, so it voids nothing.
- The hold runs from the card's issue.
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).
- Offline, gift cards wait for a connection: the card cannot be spent on an offline till.

## Tell the customer
A qualifying sale earns a gift card shortly after it is booked; it can be spent once the hold is over.
