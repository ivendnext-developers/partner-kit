---
id: optical-prescription-at-pay
title: Lenses sold only against an eye prescription in date
area: till
topic: questions-during-the-sale
asks: Contact lenses and prescription spectacle lenses are sold only to a customer whose eye prescription is on file and still valid
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/optical_prescriptions.md
sample: samples/s42_optical_prescriptions
request: -
verified: 2026-10-23 · bench
---
## What you build
Eye prescriptions as the shop's own records (spectacles or contact lenses, the test date and *Valid until*, each eye's values), a mark *Sold against a prescription* on the lens item groups, and a service that answers the check before payment. A marked line is paid only when the sale's customer has a prescription of its kind in date; otherwise the cashier reads which line, and the day the last one ran out. The service reads two fields of a prescription (its kind and *Valid until*), never a lens value.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- A sale made in Desk, on the Desk POS screen or through the API is not checked.
- When the service is down, or the till is offline, the sale is paid and flagged for review.
- At most three checks per POS Profile, 10 seconds together; this app takes one per profile.
- An insurer's or vision plan's share of the payment is not part of it.

## Tell the customer
Your tills sell contact lenses and prescription lenses only to a customer whose prescription is on file and in date, and say which line and why when it is not.
