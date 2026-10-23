---
id: reason-asked-on-reject
title: A reason asked when a document is rejected
area: documents
topic: approvals
asks: The approver must give a reason when rejecting a purchase order, and it is kept on the document
status: ready-with-limits
door: desk-action
blocked-by: -
recipe: recipes/desk_action.md
sample: samples/s11_approvals
request: -
verified: laptop 2026-10-16 · S11's reject, 6 tests (the reason before the workflow, a second press, a short reason, a refused transition, a lost answer) · not run on a retailer's iVendNext
---
## What you build
A Desk action *Reject with reason* on the document with one required input, *Reason* (Small Text). Your service writes the reason and who pressed into fields your manifest added, then moves the document with iVendNext's workflow call (`apply_workflow`); a save rule, added with the button, refuses a rejected document with no reason. Recipe section *A reason asked before a document is rejected*; sample S11's `reject`.

## Limits
- The user presses the action instead of the workflow's own reject button. Take the reject transition away from those roles (configuration), or that button still rejects without a reason.
- A user presses it: nothing asks for a reason when a document is rejected another way (an import, the API).
- Your service rejects with its own key, as its integration user: that user's role needs the reject transition, and the workflow records that user. Write the pressing user (the context carries it) into a field if the audit trail must show who rejected.
- Your service must be up: when it is down the button says so and nothing is rejected.

## Tell the customer
The approver is asked for a reason in a dialog when rejecting, and the reason is kept on the document.
