---
id: insurance-co-payment
title: An insurance co-payment at the till
area: till
topic: payment
asks: Insurance co-payment: the insurer pays part of a prescription and the customer the rest
status: ready-with-limits
door: payer
blocked-by: -
recipe: recipes/third_party_payer.md
sample: samples/s43_third_party_payer
request: -
verified: run by the product 2026-10-25 and 2026-10-26 (POS train T18's lane and train walks, phone, counter and tablet frames: the Payer tile, a cover taken, the payer's share billed to it and the rest paid in cash or by card, a line the payer refuses, the plan's prices, a return giving the payer's share back, the day closed); not run by a kit sample
---
## What you build
A service for the *payer* extension point (`payer/1`, POS version 2.1.0.666 and later). When the cashier presses **Payer** on a named customer's sale, the till asks your service which covers the customer holds, then what you pay on each line. Your share is booked as owed by your own customer record on the retailer's books, never taken as a payment, and the customer pays the rest with the till's other tenders. A return gives your share back, and `ivendnext_mpos.api.v1.payer_bill_back` bills a rejected claim back to the customer. Sample S43 (`samples/s43_third_party_payer`) keeps the payers, plans, members and claims as records; the contract and its sixteen samples are on the payer page (`contracts/pages/payer.md`).

## Limits
- **Online only:** the Payer tile is not offered offline, and a payer's sale is never queued.
- One payer per sale, and one payer service per POS Profile.
- A sale whose total carries a charge on the whole sale (a service mode's charge) is never asked about: the cashier is told to take the charge off.
- The retailer picks the clearing mode, a mode of payment of its own; a manifest cannot carry it.
- No deductible or limit carried across sales, and no pre-authorisation: those are your service's to do.

## Tell the customer
The cashier presses Payer, the insurer's share is billed to the insurer on your books, and the customer pays only their own share.
