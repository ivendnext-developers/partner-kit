---
id: gift-card-on-spend
title: A gift card for a big spend
area: customers
topic: loyalty-and-wallets
asks: A gift card for a spend over a threshold, spendable after a hold, with its number sent to the customer by e-mail or text
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/gift_card_on_spend.md
sample: samples/s25_gift_on_spend
request: -
verified: carried 2026-10-16 · not re-run; message limit added 2026-11-22, not run
---
## What you build
An outside app reads booked sales from the feed and issues the retailer's own gift card, released after the hold.

## Limits
- The card is made after the sale, not on its receipt.
- The kit has no way yet to send the number to the customer (the recipe, step 8). A route to try: a record of yours holding the customer's mobile number or e-mail, and the retailer's own Notification, as the card *post-sale-feedback* does by SMS. Not run for a gift card, and a Notification fires when your app writes the record, not at the till.
- A return without the receipt names no sale, so it voids nothing.
- The hold runs from the card's issue.
- The kit's samples read the shared feed, whose key is not limited to one app (a feed scoped to your app is an extension point, chapter 9).
- Offline, gift cards wait for a connection: the card cannot be spent on an offline till.

## Tell the customer
A qualifying sale earns a gift card shortly after it is booked; it can be spent once the hold is over.
