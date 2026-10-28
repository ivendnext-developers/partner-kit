---
id: controlled-drug-register
title: The controlled-drug register, and any register of regulated stock
area: documents
topic: own-records-and-fields
asks: Keep the controlled-drug register the law asks for (or the liquor, tobacco or duty-free register)
status: ready-with-limits
door: register-books
blocked-by: -
recipe: recipes/regulated_register.md
sample: samples/s41_regulated_register
request: -
verified: run by the product 2026-10-23 to 2026-10-26 (the register lanes' walks and POS train T17's walk, phone, counter and tablet frames and Desk: books installed from a package, a till sale writing one numbered line per book, a sale refused before the tender when the balance would go below zero, a receipt and its cancel writing a correction line); run by kit sample S41 0.2.0 on 2026-10-28 (installed from a package, and as an update from 0.1.3; Kenya's books on the till in three frames and on the Desk; Jordan's official book printed in Arabic)
---
## What you build
Your market's books as data in your manifest (`register_books`, POS version 2.1.0 and later): which items each book takes, which movements enter it, how its lines are numbered and corrected, and the columns it prints with the source of each. From then on every document that moves a declared item writes one line per book in the same save, numbered with no gap, with a running balance where the book keeps one, and never edited: a cancel writes a correction line. Sample S41 declares the pharmacy books of eight markets. The steps (declare, map the stores, count the opening, correct, print) are in the regulated register recipe; the keys and refusals are on the register books page.

## Limits
- Every layout in the sample is a first draft, not certified for the country: you check it against the law before a customer relies on it.
- A routing rule has at most three conditions, all of which must hold, on a column of the register's line.
- An update cannot change a book: a corrected book ships under a new id, which numbers from 1.
- The retailer maps its warehouses to each book's register store before the first sale; a manifest cannot.
- Sample S41 (0.2.0) installs eight markets' pharmacy books on the door from data sets, Kenya's three first: start from it, or build a book from the regulated register recipe and the register books page.
- An article first stocked after its book is switched on is not checked against the balance until a count sets it.

## Tell the customer
Every sale, receipt and transfer of a controlled item writes its line in the register as it is saved, and the book prints in your country's layout for an inspector.
