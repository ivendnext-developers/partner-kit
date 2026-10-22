---
id: minimum-shelf-life-at-receipt
title: A minimum shelf life on a batch received
area: stock
topic: batches-and-expiry
asks: Refuse a batch whose remaining shelf life is below our minimum, unless a named role accepts it
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: recipes/save_rules.md
sample: samples/s40_expiry_recall
request: -
verified: run by the product 2026-10-17 (its walk in Desk's own form: a stock user's batch below the limit refused, the settings role's holder let through, a description edit saved, an expiry edit judged again, the limit changed in the settings record and followed); not run on a sandbox
related: value-worked-out, settings-drive-rules, recall-and-disposal
---
## What you build
From POS build 2.0.0.654: three Batch fields (days left, shelf days, shelf %), a settings record with the limit and a role, and five save rules, in order: two `days_between` (days left, shelf days), a `percent`, a limit *shelf days > 0* judged at every save, and a limit *shelf % ≥ limit* judged on change, its limit and role read from the settings record (`contracts/pages/save_rules.md` §8, the worked example; `recipes/save_rules.md`).

Sample S40 judges the goods receipt itself instead, with a document check: a minimum per item or for the shop, an exemption per item, a Letter of Undertaking per line with its days, and the expiry printed on the pack (`recipes/expiry_recall.md`).

## Limits
- A batch a receipt makes, or a split makes, is judged at its first later save, not at the receipt; a bulk batch insert runs no rule.
- A save that empties a date passes and leaves the shelf % empty: list the batches with an empty shelf % before switching the rules on, and after, as a standing check.
- Switch the *shelf days > 0* limit off together with its derived rule.
- A figure the limit judges is never made mandatory.

## Tell the customer
A batch with less shelf life left than your minimum is refused when it is saved, unless the person saving holds the role you name; a batch made by a receipt is judged at its first later save.
