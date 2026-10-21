---
id: units-as-serial-numbers
title: Every pack's own code checked on every stock document
area: stock
topic: batches-and-expiry
asks: Each pack carries its own printed code; check it when stock is received, moved, counted and sold, and tell a lost pack from a sold one
status: ready-with-limits
door: configure
blocked-by: -
recipe: samples/s30_units_as_serials/README.md
sample: samples/s30_units_as_serials
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.650 · received by paste and CSV, transferred, sold, refused sold again, returned, counted with one missing, refused in Defective, the report, the migration's dry run; a unit from either lot sold at the till run by the product 2026-10-18 (POS train T12's walk: each unit booked with its own batch, a set's unit too); not run: the migration's apply, the current undo, an issue, a resale after a return, offline, a Purchase Receipt
related: unit-code-at-scan, imei-per-phone-sold
---
## What you build
Configuration: each code is a serial number of an item with both batches and serial numbers, and no Serial No Series. Sample S30 adds the set-up script, a migration from a unit table of your own, and a report that tells a counted-out unit from a sold one.

## Limits
- At the till, from POS build 2.0.0.654, each unit is booked with the batch its own Serial No carries; a unit whose Serial No has no batch is refused. Before that build, a unit from a lot other than the one iVendNext picks first is refused at payment.
- A unit from an expired batch is refused at payment on its own line, not inside a set: keep expired stock off the shelf. A promotion on named units names their batches too.
- A count marks the units it did not find *Delivered*, as a sale does: the sample's report tells them apart.
- Defective is a store, not a status; the till refuses a unit there as another store's.
- An item that already has stock cannot be switched to serial numbers: the units move to a new item.
- Issued and counted-out codes can be received again; a code sold at the till and received again by a receipt, not a return, stays refused at the till.
- Till sales read *Active* until the day's sales are posted; a site needs a default Company.
- A later version of iVendNext names a serial number by a generated name: the sample's lookups by name then read the code field instead.
- Offline: not run (the cashier scans the item, then the code as its serial).

## Tell the customer
Every pack's code is checked by iVendNext on receipts, transfers, counts, sales and returns; at the till each pack is sold with its own lot, from iVendNext POS build 2.0.0.654.
