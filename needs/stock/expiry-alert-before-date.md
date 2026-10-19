---
id: expiry-alert-before-date
title: A notification a number of days before a date on a shop's record
area: stock
topic: alerts-and-reorder
asks: A notification a number of days before a date on a shop's own record, such as a batch's expiry
status: ready-with-limits
door: configure
blocked-by: -
recipe: guide/04_configure_first.md
sample: none
request: P-NOTIFYDATE
verified: run on a sandbox 2026-10-16 · POS 2.0.0.647 · a Desk notification of the kind *Days Before* on a batch's expiry date saved (then deleted); not run: the notification firing, a manifest shipping it
---
## What you build
A notification in iVendNext Desk, of the kind *Days Before*, on the batch's expiry date, set by the shop's own administrator; the system notification or e-mail goes to a role.

## Limits
- It is set in Desk, one shop at a time: a manifest cannot ship a notification on a shop's own record (chapter 7), so a partner who wants it installed for many shops asks for P-NOTIFYDATE, or sets it with the shop's administrator.
- It was saved on a sandbox but never fired (the site has no batch with an expiry date), and a batch with no expiry date raises nothing.

## Tell the customer
The shop's administrator can set a notification a number of days before a batch expires; we have not yet watched one fire.
