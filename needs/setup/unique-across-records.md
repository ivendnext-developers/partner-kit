---
id: unique-across-records
title: A value unique across all records
area: setup
topic: roles-and-data-rules
asks: A tax number on one customer only
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: contracts/pages/save_rules.md
sample: none
request: P-RULES2
verified: carried 2026-10-16 · not re-run (the rule kind read in the product's save-rules page at POS origin/development; a manifest declaring it passes tools/manifest/validate.py)
---
## What you build
A save rule of kind *unique across*: the value of one field is on no other active record of the type. The product also takes up to three scope fields (for example the company). It holds on every save: Desk, import and the API. The kit's copy of the save-rules page, written before this kind merged, lists seven kinds and does not describe it; the product's page does, and the shop's install screen is the check.

## Limits
- The kit's copy of the checker does not take scope fields yet (probed: it refuses them); the plain form passes. Scope arrives with the next re-copy of the product's checker.
- On a table above 10,000 records, the field must be indexed.
- It is a rule, not a database constraint: two saves at the same moment can both pass.
- A cancelled record holds no value; an empty value passes; the comparison follows the database's case rules.
- It checks the record itself, never a table's rows (card no-value-twice-in-lines does that).
- On a till sale and the till close a save rule only flags, never refuses.
- Not run: the kit's sandbox has not exercised this kind.

## Tell the customer
A customer's tax number can be held on one active customer only; a second one is refused when it is saved.
