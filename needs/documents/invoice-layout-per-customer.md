---
id: invoice-layout-per-customer
title: A layout of its own for each customer's invoice
area: documents
topic: layouts-and-labels
asks: A layout of its own for each of a few distributors' invoices
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/print_pack.md
sample: samples/s29_print_pack
request: P-PRINTBYPARTY
verified: run on a sandbox 2026-10-16 · POS 2.0.0.650 · draft invoices, with and without tax: one template printed three customers' layouts and a plain one for a stranger, by name and as the invoice's default, and the per-customer set printed each format; the customer record has no print-format field; not run: a submitted invoice, a return, the print and e-mail dialogs, the shop's PDF of an invoice
---
## What you build
Print formats in a manifest, on the sales invoice: one template that branches on the customer picks the layout by itself, or one format for each customer that the user chooses.

## Limits
- The back-office invoice only: the till's receipt is separate.
- Nothing chooses a format by customer on its own (the customer record has no print-format field, read on a sandbox), so the branch lives in the template, and the shop's administrator makes that template the invoice's default (a manifest cannot set the default): ask for P-PRINTBYPARTY. With one format for each customer, a person picks it every time.
- A layout reads only the invoice's own fields; a figure the invoice does not carry cannot be printed.
- Once the branch format is the invoice's default, it is every customer's invoice: any customer not named gets the plain layout, so that layout must carry what the shop's current invoice does (tax lines, tax numbers).
- A copied layout gets none of our later fixes.

## Tell the customer
Each distributor's invoice prints in its own layout from the back office; the till's receipt is not part of it.
