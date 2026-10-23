---
id: lab-orders-as-records
title: Lab orders kept as records, with a workflow
area: documents
topic: own-records-and-fields
asks: Optical lab orders tracked in iVendNext and sent to the lab
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/optical_prescriptions.md
sample: samples/s42_optical_prescriptions
request: -
verified: 2026-10-23 · bench
---
## What you build
Lab orders as your manifest's own record type, made from the customer's prescription (its lens values copied, read only), with a workflow *Ordered → Sent to lab → Ready to collect → Collected* and a job sheet to print. A tick the workflow sets, *Ready to collect* (unticked again for a remake), lets the retailer's own Notification tell the customer; an outside app of yours can send the order to the lab's own system.

## Limits
- Who may edit a record in a workflow state is checked in the browser only: follow the four safeguards in chapter 13a.
- A manifest's notification goes only to the retailer's own users: the message to the customer is the retailer's own Notification.
- The order shows its prescription's values as they were at its last save.

## Tell the customer
Each lab order is tracked from the order to the lab and back until the customer collects it, with a job sheet for the lab.
