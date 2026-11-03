---
id: approval-by-store
title: Approvals by store
area: documents
topic: approvals
asks: Each store's purchase orders or transfers are approved by that store's manager
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/approvals_stores.md
sample: samples/s14_approvals_stores
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
A workflow on the document, and one **User Permission** per person on their store, so a manager sees and approves only their own store's documents. Set in Desk, with no code; a manifest installs the workflow on every site. Sample S14 shows it with a store manager's limit and head office above it, on a price change.

## Limits
- A workflow cannot run on the till's own records, such as POS Invoice.

## Tell the customer
Each store's documents go to that store's approver.
