---
id: outside-fiscal-result
title: An outside fiscal service's result on the sale
area: integrations
topic: payments-and-fiscal
asks: The tax authority's result, QR code and seal on each sale and receipt
status: ready-with-limits
door: fiscal-reader
blocked-by: -
recipe: contracts/pages/fiscal_reader.md
sample: none
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
A fiscal reader: the outside fiscal service writes its result on the sale, and the receipt prints only when it is back.

## Limits
- When the fiscal service is down, the sale waits and its receipt is held until a result arrives; the till does not retry for you.

## Tell the customer
Each receipt carries the tax authority's result, from your fiscal service.
