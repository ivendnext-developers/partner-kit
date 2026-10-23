---
id: payment-methods-for-sale
title: Only some payment methods for a sale or a customer
area: till
topic: payment
asks: Delivery-platform customers paying only by the platform's method, no on-account for a cash customer, and methods that may not be combined
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/payment_method_rules.md
sample: samples/s46_payment_method_rules
request: -
verified: run on our test bench 2026-10-23 · a rule per customer group leaving methods off the till's payment screen, a group taking the rule above it, a sale with nothing left to pay with refused
popular: yes
---
## What you build
A rule record per customer group (*Only these payment methods* or *Every payment method but these*), and a service that answers the check before payment with `allow` and `exclude_tenders`: the payment methods this sale's customer may not use. A group with no rule takes the rule of the nearest group above it.

## Limits
- Answered when the cashier presses Pay, not when the line is entered.
- The excluded methods show dimmed, with your reason.
- Refunds are not judged. An exchange's new items are, as a sale: a rule must leave store credit in, or that group cannot exchange.
- A group's own rule replaces the rule above it entirely.
- Two methods together in one sale are not judged: the check answers before a method is picked.
- Leaving out the store's first card method stops card payments at the till.

## Tell the customer
At Pay the till offers only the payment methods this sale and this customer may use; the others are dimmed with the reason.
