---
id: merge-count-documents
title: Merge several count documents into one
area: stock
topic: counts
asks: Merge several stock counts into one
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/merge_documents.md
sample: samples/s28_merge_and_history
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.648 · the sample, pressed through Desk's server call: two drafts merged into one (12 + 7 = 19, the latest count's rate), the Last rule, a retry after a timeout made no second draft, a submitted count refused by the shop; not run: the button in Desk's screen, serial or batch rows
---
## What you build
A desk action on the count list: the ticked rows go to your service, which re-reads them and writes one merged draft through the record API.

## Limits
- Drafts only: the shop refuses a submitted or cancelled count before your service is called (run). The list allows 100 per press, but each is read and commented inside Desk's 10 seconds: keep it to a handful.
- The rule for the same item in the same warehouse (add them, or the latest count's) is the customer's, kept in a settings record; the valuation rate, posting date and posting time are the latest count's (run).
- The source counts stay drafts with a comment *merged into ⟨name⟩*: cancel or delete them, or the stock is counted twice (run).
- A row with serial numbers, or with its batch or serials in a bundle, refuses the merge (laptop only).
- Desk waits at most 10 seconds: a merge of two counts took 5.3 to 5.7 seconds with the service far from the shop; run it near the shop. A retry from the same dialog finds the draft already made (run), unless the shop saved it after the service stopped waiting: then look for a second draft.

## Tell the customer
Several counts become one draft that a person checks before it is submitted; a submitted count is left alone.
