---
id: list-columns
title: A list column the retailer wants on a record's list
area: setup
topic: roles-and-data-rules
asks: A column the retailer wants on a record's list
status: ready-with-limits
door: configure
blocked-by: -
recipe: guide/04_configure_first.md
sample: none
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 · a list query naming a count's header field *difference amount* was accepted; not run: choosing the column in the Desk list's own column settings
---
## What you build
The user picks the columns in the list's own settings in iVendNext Desk, or an administrator sets the record type's list settings.

## Limits
- Only the record's own fields can be a column; a total of its item rows cannot (the card count-list-totals).
- Picking the column by hand in the list's own settings was not run, so whether a column can be set for every user is not promised.

## Tell the customer
Users pick the columns they want on a list; a total of a document's rows is a separate piece of work.
