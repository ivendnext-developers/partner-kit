---
id: recall-by-serial
title: A recall by serial number, traced to the customers who bought the units
area: stock
topic: batches-and-expiry
asks: When a maker recalls units by serial number, find the serials sold and the customers who bought them, and stop the rest being sold
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/repairs_by_serial.md
sample: samples/s58_repairs_by_serial
request: -
verified: 2026-10-29 · bench
related: recall-and-disposal, repairs-by-serial
---
## What you build
Nothing new. **Who bought them:** the engine's **Serial No Ledger** (Desk › Stock), the recalled item and, to narrow it, the serial number: each movement out by a sale names the customer it was sold to. **Stop the rest:** a Stock Entry of type **Material Transfer** moves the recalled units still in stock to a store no till sells from (a warehouse on no POS Profile); the till sells a serial only from its own store, so it refuses them. **The units brought back:** with sample S58, each is a repair of kind *Recall work* under its serial.

## Limits
- A till sale shows in the ledger once its day's sales are booked to stock: at once on some sites, at the day's close on others.
- A walk-in sale names the store's walk-in customer: no one to contact.
- The report is on the stock ledger: Stock User opens it, Sales User alone does not. It shows customers' names: give it only to whoever runs the recall.
- A recall by lot (food, medicine) is a different need: sample S40, *Expiry and recall*.

## Tell the customer
When a maker recalls units, the store finds who bought each recalled serial from its own stock ledger and moves the rest out of the tills' reach; each unit brought back is recorded under its serial.
