---
id: expiry-alert-before-date
title: A notification a number of days before a date on a retailer's record
area: stock
topic: alerts-and-reorder
asks: A notification a number of days before a date on a retailer's own record, such as a batch's expiry
status: ready-with-limits
door: manifest
blocked-by: -
recipe: guide/07_manifests.md
sample: samples/s27_stock_alerts
request: -
verified: run on a sandbox 2026-10-21 · POS 2.0.0.658 · S27's reminder package installed: a Days Before notification on Batch, 30 days before its expiry date, to the Stock Manager role, by e-mail, read back, then uninstalled; not run: a message sent (the daily send rests on the product's tests)
---
## What you build
From POS build 2.0.0.654, a manifest ships the reminder: a notification on Batch, *Days Before* its expiry date, to a role, by e-mail or the bell (`guide/07_manifests.md`, *A reminder before or after a date on a retailer's record*). Sample S27 carries the package (`batch_expiry_package.json`). Before that build, the retailer's administrator sets the same notification in Desk.

## Limits
- No cap: one message per batch on the day.
- Every holder of the role, in every store, receives every batch: no data filter exists on this version.
- To a role only, by e-mail or the bell; the message is plain text and the record's own fields.
- A template error skips one message; an error outside it (a batch deleted mid-run, a date field removed later) stops that day's run.
- The daily scheduler sends it; a batch with no expiry date raises nothing.

## Tell the customer
We install a reminder a number of days before each batch expires, to the role you name, in every store; it is one message per batch, with no filter by store.
