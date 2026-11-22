---
id: wish-list-and-messages-to-a-customer
title: A customer's wish list, and a message to the customer from the store
area: customers
topic: history-and-crm
asks: Our associates keep each customer's wish list and send the customer a message, clienteling, when an item comes back in stock or goes on sale
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/post_sale_feedback.md
sample: samples/s49_post_sale_feedback
request: -
related: own-crm, post-sale-feedback, customer-history-on-till
verified: read against the kit's samples S49 and S57 and the till's customer card 2026-11-22 · not run for a wish list
---
## What you build
Two parts. The wish list is your manifest's own record type, shaped as S57's donation (`recipes/donation_intake.md`): the customer, the item, a size or colour if wanted, the day and who added it. The message is S49's route: a Desk button on a rule of yours, whose service picks the customers to tell and writes one message record each with their mobile number or e-mail, and the retailer's own Notification sends it by SMS, e-mail or WhatsApp. Whether an item has come back or gone on sale is read by your service at the press, from the stock and prices it reads over the record API.

## Limits
- Not run: no sample keeps a wish list. The message half is S49's, run on a test bench by SMS on 2026-10-24; e-mail and WhatsApp were not run.
- A press, not a schedule: the messages go when an associate presses, and what does not fit its 10 seconds waits for the next press.
- The associate adds to and reads the list in Desk. At the till only a page of yours, opened by a till key with a customer and an item on the sale, shows it (the card *customer-history-on-till*): online, and not run for a wish list. A seller who never opens Desk adds nothing to it.
- iVendNext's own SMS settings, e-mail account or WhatsApp app send the message: the kit brings no gateway.
- A customer who asked to stop is never messaged: your own record must keep that, as S49's does.

## Tell the customer
Each associate keeps a customer's wish list in Desk, and the customer gets a message from the store through the retailer's own messaging whenever the associate presses to send.
