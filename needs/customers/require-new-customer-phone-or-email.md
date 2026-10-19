---
id: require-new-customer-phone-or-email
title: A new customer's phone or e-mail made required
area: customers
topic: customer-records
asks: Every new customer must give a phone number or an e-mail
status: ready-with-limits
door: field-rules
blocked-by: -
recipe: recipes/field_rules.md
sample: samples/s21_field_rules
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
A field rule, set in POS Studio's Fields tab or declared in a manifest, requires the field when the till makes a customer; the server holds it where it writes.

## Limits
- Required only when the till itself makes the customer: one made in Desk, by an import, through the record API or by another app is not checked.
- Offline, a customer added without the field is still made when the sale drains, and the Sales to review report lists it.

## Tell the customer
The till asks every new customer it makes for the phone or e-mail; customers made elsewhere are not checked.
