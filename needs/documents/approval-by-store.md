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
verified: 2026-11-04 · sandbox: an order for one store is hidden, not opened and not approved, and one with no target warehouse is listed; opening an order with no target warehouse: not run
---
## What you build
A workflow on the document, and one **User Permission** per person on the record that names their store, so a manager sees and approves only their own store's documents. Set in Desk, with no code; a manifest installs the workflow on every site. Sample S14 shows it with a store manager's limit and head office above it, on a price change.

## Limits
- A document is fenced only by a store it names: Purchase Order has no store of its own, so fence on its target warehouse (*Set Target Warehouse*). A User Permission on that warehouse hides the other warehouses' orders from the approver, who cannot open or approve one. An order with no target warehouse shows in every approver's list, and opens only for an approver whose store is on all its rows. An order for several stores has no target warehouse, so it needs an approver with no User Permission.
- A workflow cannot run on the till's own records, such as POS Invoice.

## Tell the customer
Each store's documents go to that store's approver.
