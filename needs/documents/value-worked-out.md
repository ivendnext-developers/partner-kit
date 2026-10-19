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
- P-RULES4 adds days between two dates to the derived rule, and to the limit rule a value judged when it changes, a row rule that reads its header and a limit read from a settings record, when it ships.

## Tell the customer
The field is worked out from the others each time the record is saved.
