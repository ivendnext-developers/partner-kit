---
id: no-value-twice-in-lines
title: No value twice in a document's lines
area: documents
topic: checks-on-save
asks: The same item or code may not appear twice in one document
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: contracts/pages/save_rules.md
sample: none
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
A save rule of kind *unique in rows*, held on every save.

## Limits
- On a till sale and the till close a save rule only flags, never refuses.

## Tell the customer
A document with the same value on two lines is refused when it is saved.
