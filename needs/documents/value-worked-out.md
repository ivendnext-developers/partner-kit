---
id: value-worked-out
title: A value worked out from others
area: documents
topic: checks-on-save
asks: A field filled in from other fields when the record is saved
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: contracts/pages/save_rules.md
sample: none
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
A save rule of kind *derived*, held on every save.

## Limits
- On a till sale and the till close a save rule only flags, never refuses.
- From POS build 2.0.0.654 the derived rule also works out a total or a count of a table's rows and the days between two dates; a limit can be judged when its value changes, a row rule can read its record (`parent.`), and a limit can be read from a settings record (`contracts/pages/save_rules.md`).
- A worked-out figure is shown as a number, never money.

## Tell the customer
The field is worked out from the others each time the record is saved.
