---
id: check-before-document-submit
title: Your system's answer before a back-office document is submitted
area: documents
topic: checks-on-save
asks: A purchase order blocked by data our ERP holds; a goods receipt checked against the supplier's terms
status: not-yet
door: request
blocked-by: extension-point
recipe: recipes/check_by_workflow.md
sample: none
request: P-DOCCHECK
verified: carried 2026-10-16 · not re-run
---
## What you build
Not yet as its own extension point. Today: a workflow step only your service can take, after its check passes (the recipe), or a Desk action a user presses.

## Limits
- Today, with a workflow: the user waits a few seconds, and your service must be up for back-office submits.
- Today, an outside app finds a problem only after the save.

## Tell the customer
A back-office document can be held for your system's check today through a workflow step; a direct check is coming.
