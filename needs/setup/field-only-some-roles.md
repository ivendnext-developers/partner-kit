---
id: field-only-some-roles
title: A field only some roles read or change
area: setup
topic: roles-and-data-rules
asks: Only the pharmacist may see a patient's ID number, and only the manager may change a supplier's bank details
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/manifest.md
sample: none
request: -
verified: run by the product 2026-10-24 (the role-limited field lane's walk, phone, counter and tablet frames: a Customer field read and written by one role only, found by search and shown on the customer's profile for that role, absent for a cashier without it, and never stored on the till's device); not run by a kit sample
related: permissions-by-role, extra-fields-on-shop-documents
---
## What you build
A field your manifest adds carries `write_roles` (who change it, and so read it) and `read_roles` (who read it), from POS version 2.1.0; the installer gives it a permission level of its own. The keys and refusals: the manifest recipe, *A field only named roles read or change*.

## Limits
- Only a field your manifest adds: a field iVendNext already has keeps the retailer's own permissions.
- An update cannot change the roles of a field already installed; a record type has nine levels, so group limited fields into few role sets.
- System Manager reads a field limited by `read_roles` only if you name it.
- An Item field limited to roles is never shown on a till or a receipt, for anyone.
- A print format, notification, report, card or chart of the same manifest may not name a field only some roles read; a register book's column is not checked for one, and prints it to whoever may print the book.

## Tell the customer
The field is changed only by the roles you name; when you limit reading too, a user without those roles does not see it, at the till or in Desk.
