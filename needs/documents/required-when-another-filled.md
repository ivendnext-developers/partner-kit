---
id: required-when-another-filled
title: A field required when another holds a value
area: documents
topic: checks-on-save
asks: A field must be filled when another field holds a value
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: contracts/pages/save_rules.md
sample: none
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
A save rule of kind *required when*, held on every save: Desk, imports and API writes. (The retailer's own *mandatory depends on* is checked in the Desk form only.) From POS build 2.0.0.654 a rule on a table's rows may read its record: on Stock Entry, `items.material_request` is required when `parent.purpose = Material Transfer` (`contracts/pages/save_rules.md` §8).

## Limits
- On a till sale and the till close a save rule only flags, never refuses.
- A row rule is refused with the row's number, *"Row 2: Material Request is required."*; the record's own fields only, through `parent.`.

## Tell the customer
The record cannot be saved without the field when the other holds a value.
