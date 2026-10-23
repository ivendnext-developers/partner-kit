---
id: check-before-document-submit
title: Your system's answer before a back-office document is submitted
area: documents
topic: checks-on-save
asks: A purchase order blocked by data our ERP holds; a goods receipt checked against the supplier's terms
status: ready-with-limits
door: document-check
blocked-by: -
recipe: recipes/document_check.md, recipes/check_by_workflow.md
sample: samples/s34_po_check
request: -
verified: run on a sandbox 2026-10-21 · POS 2.0.0.656 (install, the down answer, a standard fill field refused at save); the service's own answers proven on the laptop against the product's contract
---
## What you build
A document check on the record type: when it is submitted, from Desk, an import or the API, your service allows it, refuses it with your reason, asks the user, asks for approval by a role, or fills fields the retailer added. S34 checks purchase orders against an ERP.

## Limits
- Back office only: never a till sale, and never a record the till's own booking writes.
- The user waits for your answer: at most 10 seconds for all of one submit's checks.
- `fill` writes only a field the retailer added (a field your app adds counts), never a standard field or money.
- An import or bulk submit that runs in the background cannot show a question: answer allow or refuse there.
- On a POS app from before train T11 (2026-10-16), use a workflow step only your service can take (the second recipe).
- Not run on a sandbox: your service's own refuse, approve and fill answers; the laptop tests prove them against the product's contract.

## Tell the customer
Each purchase order is checked by your ERP before it is submitted: a held supplier is refused, an order over budget needs a manager's approval, and a clear order carries the ERP's number.
