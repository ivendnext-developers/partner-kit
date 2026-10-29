---
id: repairs-by-serial
title: Repairs and service history by serial number
area: documents
topic: own-records-and-fields
asks: Each repair, test and spare part kept against the unit's serial number, from intake to hand-over, with the unit's whole service history in one place
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/repairs_by_serial.md
sample: samples/s58_repairs_by_serial
request: -
verified: 2026-10-29 · bench
related: recall-by-serial, donation-intake
---
## What you build
A repair as your manifest's own record type, kept against a Serial No: the item and its warranty date read from the serial, the customer and their phone read from the customer, the fault, the condition at intake, the tests and their results, the work done and the parts fitted with their own serials. A workflow *Received → In repair → Ready to collect → Collected* (or *Cancelled*) and a save rule that then locks everything the slip prints, on every door. Every repair is listed under its serial number, its customer and the sale that paid for it; a print format gives the repair slip with a unit tag; a report lists the open repairs by the date promised; a field on Stock Entry names the repair a Material Issue's parts went to.

## Limits
- The app holds no charge: the till charges the repair as a service item, and the repair names the sale. A quote the customer approves first, or a deposit, is a version of your own.
- The repair is written in iVendNext Desk; a till key that takes a unit in at the till is a version of your own.
- Store staff find serials through *Select* on Serial No, which the retailer gives them (Read unticked).
- A manifest's notification goes only to the retailer's own users: telling the customer the unit is ready is the retailer's own Notification.

## Tell the customer
Each repair is recorded against the unit's serial number, from the counter to the hand-over, with the tests, the work and the parts; the unit's whole history is one list under its serial, and the customer gets a slip.
