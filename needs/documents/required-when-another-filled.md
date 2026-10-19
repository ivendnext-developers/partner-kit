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
A save rule of kind *required when*, held on every save: Desk, imports and API writes. (The shop's own *mandatory depends on* is checked in the Desk form only.)

## Limits
- On a till sale and the till close a save rule only flags, never refuses.

## Tell the customer
The record cannot be saved without the field when the other holds a value.
