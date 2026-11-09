---
id: vision-plan-benefits-and-claims
title: A vision plan's own rules, eligibility check and electronic claims
area: till
topic: payment
asks: A customer has a US vision plan: it pays a frame allowance and a fixed co-pay, the store checks the member is covered, and the claim goes to the plan electronically
status: ready-with-limits
door: payer
blocked-by: -
recipe: recipes/third_party_payer.md
sample: samples/s43_third_party_payer
request: -
verified: carried 2026-11-09 · not re-run
related: insurance-co-payment
---
## What you build
A payer service for the *payer* extension point (`payer/1`), one for each plan, built by a partner on sample S43. The service holds the plan's rules: a frame allowance, a fixed co-pay for the exam or the lenses, what each line may be paid on. At the till the cashier presses **Payer**, your service answers which covers the member holds and what the plan pays on each line, and the customer pays the rest with the till's other tenders. Your service asks the plan whether the member is covered, and sends the claim to the plan by the plan's own electronic connection.

## Limits
- iVendNext keeps no plan's rules, and no plan is built in: each plan has its own technical team, rules and certification, and the partner works with it.
- The eligibility check and the claim run in your service, so a plan's outage is your service's to answer (the till can refuse the payer line in your words).
- Online only: the Payer tile is not offered offline, and a payer's sale is never queued. One payer per sale.
- A rejected claim is billed back to the customer with `ivendnext_mpos.api.v1.payer_bill_back`; a claim paid later is your service's to book.

## Tell the customer
The cashier presses Payer, the plan's share is billed to the plan, and the customer pays the frame above the allowance and the co-pay.
