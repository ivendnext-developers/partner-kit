---
id: debtors-statement
title: A statement of what each customer owes
area: reports
topic: reports-and-bi
asks: A statement of what each customer owes, printed and sent on a schedule
status: ready-with-limits
door: configure
blocked-by: -
recipe: guide/04_configure_first.md
sample: none
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 · a statement for one customer with two sales rendered as a one-page PDF; with ageing on it failed; a schedule saved with no sender; not run: any send, ageing on another site
---
## What you build
The standard *Process Statement Of Accounts*: pick the customers, the layout, the dates, the frequency and the sender; the site makes the PDF and can e-mail it.

## Limits
- The plain statement rendered (opening, each sale, closing). With ageing switched on, the same statement stopped with a server error on this sandbox, though the receivables report ran: run it on the customer's site before you promise the ageing.
- The schedule sends through the site's e-mail queue, from the sender account chosen on the statement or else the user, so the site needs an outgoing e-mail account that is switched on (read from the code, not run: both sandbox accounts are off and no mail was tried).
- A customer with no e-mail address is skipped by the send (read from the code).

## Tell the customer
Each customer's statement is a PDF made on demand, and can be e-mailed on a schedule once the shop's outgoing e-mail is set up; we have not run a send.
