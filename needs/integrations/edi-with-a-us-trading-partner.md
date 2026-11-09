---
id: edi-with-a-us-trading-partner
title: EDI orders and invoices with a US trading partner
area: integrations
topic: online-shops-and-orders
asks: A big customer sends us purchase orders as EDI messages, and wants our shipping notice and invoice back as EDI
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/connected_app.md
sample: none
request: -
verified: carried 2026-11-09 · not re-run
---
## What you build
Your outside app, on the API and the event feed, between the trading partner's EDI connection and iVendNext. It reads the partner's purchase order and makes a sales order, and after the delivery and invoice are saved it sends the shipping notice and the invoice back in the partner's format. The partner's own network or an EDI service does the translating and the mailbox.

## Limits
- iVendNext holds no EDI message, mailbox or partner profile: they live in your app or in the EDI service.
- Each trading partner has its own message rules and tests before it goes live; the partner's technical team sets them.
- The feed reports a saved delivery or invoice, so the notice goes after the fact, not before the goods leave.

## Tell the customer
Purchase orders arrive as sales orders in iVendNext, and the shipping notice and invoice go back through the EDI connection; the partner certifies the connection before it goes live.
