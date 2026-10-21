---
id: limit-judged-on-change
title: A limit judged only when the value is new or changed
area: documents
topic: checks-on-save
asks: Check a limit (an item's maximum discount, say) against the ceiling only when someone sets or changes it, not on every edit of the record
status: ready-with-limits
door: event-feed
blocked-by: -
recipe: recipes/event_feed.md
sample: none
request: -
verified: laptop 2026-10-16 · the feed client's changed, 2 tests · not run on a shop
---
## What you build
Your service reads the record's events and judges the value only when it is new or differs from the last one it saw (`changed` in the kit's feed client), then flags it. Recipe section *A value judged only when it changes*.

## Limits
- The save is not refused: the value is judged seconds later and flagged.
- From POS build 2.0.0.654 a save rule's limit can be judged only when its value changes (`judge_on_change`), so the save itself is refused (`contracts/pages/save_rules.md`): use it where a refusal at the save is wanted.
- A value edited twice between two reads of the feed is judged once.

## Tell the customer
A new or changed value over the limit is flagged within seconds; existing records are not held up by unrelated edits.
