---
id: state-liquor-register-book
title: A state's liquor register book
area: documents
topic: own-records-and-fields
asks: Our state wants a book of every receipt and sale of liquor, numbered, with a running balance, printed for the inspector
status: ready-with-limits
door: register-books
blocked-by: -
recipe: recipes/regulated_register.md
sample: samples/s41_regulated_register, contracts/extension_contracts/samples/register_book/accepted/01_ledger_by_item_group.json
request: -
related: controlled-drug-register, liquor-excise-returns
verified: carried 2026-11-09 from the door's page and S41 · not run for a liquor book
---
## What you build
The liquor case of the card *controlled-drug-register*: a liquor data set of your own for S41, the books as data in your manifest, taking the items by your liquor item groups (the contract's liquor sample takes every group: name yours). Its columns, numbering and layout come from the state's own rule. Every receipt, transfer and sale of those items then writes one line per book as it is saved, with no gap, never edited; a cancel writes a correction line. The steps are in the regulated register recipe.

## Limits
- No liquor book ships. S41's eight data sets are pharmacy books, and every layout is a first draft, not certified: you read the state's rule and certify yours. The card names no state.
- S41's books read the pharmacy counter app's drug schedules. Build a liquor set without them (`build.py --sets`); that it installs alone is not run.
- A book that keeps a balance stops a till sale that would take an item below zero, once its opening is counted. A chain whose counts are loose counts first, or keeps a book of dealings with no balance.
- A delivery that is not yet a Delivery Note or invoice, such as a marketplace order, enters no book: the book reads stock movements.
- The retailer maps each warehouse to a register store before the first sale; a manifest cannot.
- A book changes little in an update: a corrected book is a new book, numbered from 1.
- A customer's details on a line are erased only when the count role presses *Erase persons' details* after the retention.

## Tell the customer
Every liquor receipt, transfer and sale writes its line in the state's book as it is saved, and the book prints in the layout your partner has checked against the state's rule.
