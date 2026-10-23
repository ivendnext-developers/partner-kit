---
id: controlled-drug-register
title: The controlled-drug register, and any register of regulated stock
area: documents
topic: own-records-and-fields
asks: Keep the controlled-drug register the law asks for (or the liquor, tobacco or duty-free register)
status: not-yet
door: request
blocked-by: extension-point
recipe: none
sample: samples/s41_regulated_register
request: P-REGISTER
verified: 2026-10-22 · bench (the columns, role and workspace) · not run (the books)
---
## What you build
Your market's books as a data set: which items each book takes, which sales or receipts enter it, its columns and its printed layout. Sample S41 declares the pharmacy books of eight markets (Kenya, Jordan, Nigeria, the UAE's Abu Dhabi, Saudi Arabia, Egypt, Ghana, Mexico), and installs today the register's own columns on the Desk sale and delivery and on the till, its approver role and its workspace.

## Limits
- The book itself is a legal record written in the sale's own save, numbered without gaps and never edited: that needs the register door in our POS app (P-REGISTER), which is not there yet. Until it is, the books are kept on paper.
- Every layout in the sample is a first draft, not certified for the country: you check it against the law before a customer relies on it.
- A routing rule has at most three conditions, all of which must hold, on a column of the register's line.

## Tell the customer
Your registers are kept in the system and printed in your country's layout for an inspector, once the register door is in your POS app; until then the columns are captured on every sale.
