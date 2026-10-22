---
id: prescriptions-as-records
title: Prescriptions kept as records
area: documents
topic: own-records-and-fields
asks: Keep each customer's prescriptions in iVendNext
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/pharmacy_counter.md
sample: samples/s39_pharmacy_counter
request: -
verified: 2026-10-22 · bench
---
## What you build
Prescriptions as your manifest's own record type, entered by a pharmacist, with an item table and an image; only pharmacists write them, and each dispensing against one is a record your service writes.

## Limits
- A manifest's record type cannot be submittable: a prescription is protected by permissions, and one edited after its first dispense is refused at the till rather than locked.
- The image is kept in the shop's site; the attach's *Is Private* tick must stay on.

## Tell the customer
Prescriptions are kept in iVendNext, with their own screen.
