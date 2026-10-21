---
id: unique-across-records
title: A value unique across all records
area: setup
topic: roles-and-data-rules
asks: A tax number on one customer only
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: recipes/save_rules.md
sample: none
request: -
verified: run on a sandbox 2026-10-21 · POS 2.0.0.656 (a second customer with the same tax id refused in its group, saved in another)
---
## What you build
A save rule of kind *unique across*: the value of one field is on no other active record of the type, within up to three scope fields (for example the customer group, or the company). It holds on every save: Desk, import and the API. The recipe's manifest installs one: one customer per tax id per customer group.

## Limits
- On a table above 10,000 records, the field must be indexed.
- It is a rule, not a database constraint: two saves at the same moment can both pass.
- A cancelled record holds no value; a disabled one still does; an empty value passes; the comparison follows the database's case rules.
- It checks the record itself, never a table's rows (card no-value-twice-in-lines does that).
- On a till sale and the till close a save rule only flags, never refuses.

## Tell the customer
A customer's tax number can be held on one active customer only (or one per customer group); a second one is refused when it is saved.
