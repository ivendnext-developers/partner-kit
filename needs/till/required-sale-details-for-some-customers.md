---
id: required-sale-details-for-some-customers
title: Sale details some customers must give before paying
area: till
topic: payment
asks: An account customer's purchase order number, an insured patient's policy number or a contractor's project required at Pay, and nothing asked of other customers
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/required_sale_details.md
sample: samples/s50_required_sale_details
request: -
verified: run on our test bench 2026-10-24 · a rule per customer group refusing Pay while a needed sale detail is empty, a group taking the rule above it, a rule held only at its POS Profiles
popular: yes
---
## What you build
A rule record per customer group naming the sale details it needs (Sale Attribute) and, optionally, the POS Profiles it holds on, and a service that answers the check before payment with `refuse` and the retailer's words while one of them is empty. A group with no rule takes the rule of the nearest group above it.

## Limits
- Answered when the cashier presses Pay, not when the customer is chosen.
- The detail must be filled, not checked: its shape is the Sale Attribute's own pattern.
- The sale's details only, not a line's.
- Refunds are not judged. An exchange's new items are, as a sale, except an exchange rung without its sale when nothing is owed.
- A detail switched off, or hidden by a field rule, cannot be filled at the till.
- An exchange's screen and a sale made from a quote have no place to fill a sale detail: fill it on the quote first; refund and ring a new sale instead of an exchange.
- A group's own rule replaces the rule above it entirely.
- Offline sales are flagged when they reach iVendNext, never refused.

## Tell the customer
At Pay the till asks for the details your rule needs for that customer's group, in your words; other customers are never asked.
