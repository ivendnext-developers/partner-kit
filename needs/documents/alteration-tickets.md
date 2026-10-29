---
id: alteration-tickets
title: Alteration and made-to-measure tickets
area: documents
topic: own-records-and-fields
asks: A garment's alteration or made-to-measure order taken at the counter, with its fitting, due date and hand-over
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/alteration_tickets.md
sample: samples/s53_alteration_tickets
request: -
verified: 2026-10-29 · bench
---
## What you build
A ticket as your manifest's own record type: the garments and what to do to each, the measurements, the next fitting, the date it is ready, the tailor, and the till sale or order it was paid on. A workflow *Taken → With the tailor ⇄ Fitting → Ready to collect → Handed over* sets a tick, *Ready to collect*, that the retailer's own Notification reads to tell the customer; a print format gives the customer's slip and the garment's tag; a report lists the tickets due. The charge and any deposit stay at the till (a service item or a line surcharge; the till's order or a layaway).

## Limits
- The ticket is written in iVendNext Desk; staff name the sale or the order on it. A till key that writes it from the basket is a version of your own.
- Who may edit a record in a workflow state is checked in the browser only: follow the four safeguards in chapter 13a.
- A manifest's notification goes only to the retailer's own users: the message to the customer is the retailer's own Notification (an SMS one names the phone in its condition, or a customer with no phone stops the save).

## Tell the customer
Each alteration and made-to-measure piece has a ticket from the counter to the hand-over, with a slip, a garment tag, its fittings and a message when it is ready.
