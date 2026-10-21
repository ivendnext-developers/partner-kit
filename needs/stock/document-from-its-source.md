---
id: document-from-its-source
title: A transfer, a delivery or an invoice made from its request or order
area: stock
topic: moves-and-orders
asks: Our service makes the stock transfer from a material request, or the delivery note or invoice from a sales order, as Desk's Create menu does
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: api/README.md
sample: none
request: -
verified: run by the product 2026-10-16 (its tests of the three names: each builds the document as Desk's Create menu does, with the caller's rights); not run on a sandbox (no submitted request or order there)
---
## What you build
From POS build 2.0.0.654, your service calls `/api/method/ivendnext_mpos.api.v1.material_request_to_stock_entry`, `sales_order_to_delivery_note` or `sales_order_to_sales_invoice` with the submitted source's name. Each answers an unsaved document built as Desk's *Create* menu builds it; your service checks or changes it, then saves it with `POST /api/resource/<record type>` (`api/README.md`).

## Limits
- The source must be submitted. Nothing is saved until your service saves it, and a draft is not booked until it is submitted.
- The key's user needs read on the source and create on the new document; with strict user permissions on, the create is checked after the mapping.
- Each call builds the whole remaining document: to take part of an order, change the quantities before you save.

## Tell the customer
Our service makes the transfer, the delivery or the invoice from your request or order exactly as Desk would, and a person, or our service, then saves and submits it.
