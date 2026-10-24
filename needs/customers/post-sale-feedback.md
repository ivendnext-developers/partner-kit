---
id: post-sale-feedback
title: Ask customers how their visit was, after the sale
area: customers
topic: customer-records
asks: After a sale the customer gets our message asking how the visit was, taps an answer, and we see the answers by store
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/post_sale_feedback.md
sample: samples/s49_post_sale_feedback
request: -
verified: run on our test bench 2026-10-24 · requests made from real till sales and texted through iVendNext's own SMS settings and Notification, an answer written once, stop these messages kept
---
## What you build
A Desk button on a rule of your own and a page your service serves. A manager presses *Send feedback requests*; your service reads the rule's recent till sales and writes one request per customer to ask, holding the customer's own signed link, and the retailer's own Notification sends it by SMS, e-mail or WhatsApp. The customer opens the link, taps one of three answers in the retailer's words, may add a comment or ask to stop, and the answer lands on the request, once. The sample S49 does it.

## Limits
- A press, not a schedule: the messages go when the manager presses (once a day is enough).
- One press makes what fits its 10 seconds; more sales wait for the next press, which says so.
- A customer is asked once in a rule's days; never the store's walk-in customer, a return, or a customer who asked to stop.
- iVendNext's own SMS settings, e-mail account or WhatsApp app and a Notification send the message: the kit brings no gateway.
- Each request holds the customer's mobile number and e-mail, on the retailer's own iVendNext.

## Tell the customer
After your visit we may send you one short message asking how it went; one tap answers it, and you can tell us to stop.
