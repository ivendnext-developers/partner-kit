---
id: id-at-customer-add
title: An ID number or date of birth asked for when the till adds a customer
area: customers
topic: customer-records
asks: The till asks every new customer for their ID number and date of birth
status: ready-with-limits
door: field-rules
blocked-by: -
recipe: recipes/field_rules.md
sample: none
request: -
verified: run by the product 2026-10-25 (the customer-field lane's walk, counter, phone and tablet frames and offline: three shop Customer fields asked on the add sheet and the edit form, a create without the required ID refused, the values stored, an offline add booked with them when the sale drained, the day closed); not run by a kit sample
related: require-new-customer-phone-or-email
---
## What you build
A field rule `show` on `customer_create` (POS version 2.1.0 and later), set in POS Studio's Fields tab or declared in a manifest's `field_rules`: the new-customer sheet and the till's customer edit ask for up to three of the shop's own Customer fields. To make one required, add a save rule (`required_when`). The rules: the field rules page, §7e.

## Limits
- Only a field the shop or an app added, of type Data, Select, Int or Date; at most three per theme.
- Required only through a save rule, never the Desk's Mandatory flag (which refuses every till create in raw words). A customer added offline, or at the receipt's contact capture, is never refused for it: a missing one is listed in *Sales to review*, since the sale is paid.
- A field only some roles write is asked only of a cashier whose roles write it, online; offline the sheet never asks for it.
- When the phone typed belongs to a stored customer, the till attaches that customer and says the other details typed were not saved on them: edit the customer to add them.
- A Select left unanswered takes its first choice: give it an empty first choice.

## Tell the customer
The till asks each new customer for the ID number and date of birth you choose, and refuses to add one without a required ID.
