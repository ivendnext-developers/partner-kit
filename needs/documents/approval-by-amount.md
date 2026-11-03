---
id: approval-by-amount
title: Approvals by amount
area: documents
topic: approvals
asks: Purchase orders or transfers over an amount need approval
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/approvals.md
sample: samples/s11_approvals
request: -
verified: POS 2.1.0.679 · S11 installed on our test bench and walked: approve submits, reject holds, the condition decides who may act
popular: yes
---
## What you build
Often nothing. **If the amount and the approver are all the customer wants, it is one record in iVendNext Desk, with no app:** **Authorization Rule**, on *Purchase Order*, based on *Grand Total*, with the amount and who approves above it. Anyone else who tries to submit an order over the amount is refused.

**If they want named steps, a Reject, mail, or the same thing on many sites,** a workflow on the document, in a manifest: sample S11, with no service and no key. Approving submits the order, and a condition on the amount decides who may act.

## Limits
- A workflow cannot run on the till's own records, such as POS Invoice: a sale must never wait for an approval nobody at the counter gives.

## Tell the customer
Documents over the amount wait for the approver before they can be submitted.
