---
id: stock-and-expiry-alerts
title: Alerts before expiry and below the minimum, and a draft transfer request
area: stock
topic: alerts-and-reorder
asks: Alerts before expiry and below the minimum stock, and a draft stock transfer request made from them
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/stock_alerts.md
sample: samples/s27_stock_alerts
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.648 · the sample: 2 alerts and 1 draft with 2 lines, a second run nothing new, the bell, a hand-submitted request left alone; not run: a Purchase row, no clearance warehouse
---
## What you build
An outside app on a schedule reads stock, reorder rows and batches over the record API, writes each alert on a record type of your own (a manifest notification announces it), and makes one draft transfer request per store and day.

## Limits
- The standard automatic reorder submits the request, never a draft (run, card low-stock-reminder): a draft needs this app.
- A manifest's notification cannot run on a shop's own record, such as a batch (chapter 7), so the alert is a record of your own and the notification is on that; the shop's administrator can set a notification on a batch in Desk (the card expiry-alert-before-date).
- A transfer request has no batch column and holds an item once (run: a second row of one item was refused): batches of one item share a line whose description names them; an item low and near expiry in one store the same day gets one line (not run).
- A batch's quantity per store is read from its stock movements' batch records; with no right to read them the alert says the batch's total and makes no line.
- The shop's built-in Administrator is never told by role: give the alerts role to named people (run).
- A draft reserves nothing; once a person submits it, the projected stock counts it and the item stops being low (run).
- The reports *Stock Projected Qty* (switched off on both sandboxes) and *Batch Item Expiry Status* are not used: the sample reads records only.

## Tell the customer
You get an alert before stock runs low or a batch expires, and a draft transfer request that a person approves before it becomes a real one.
