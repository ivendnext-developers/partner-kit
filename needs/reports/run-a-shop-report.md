---
id: run-a-shop-report
title: Run one of the retailer's own reports from our service
area: reports
topic: reports-and-bi
asks: Our service runs one of the retailer's reports, with filters, and reads the rows
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/shop_reports.md
sample: none
request: -
verified: run on a sandbox 2026-10-21 · POS 2.0.0.658 · run_report on a report (59 rows); a prepared report answered nothing before a run, then prepare_report queued a run, and run_report read it by its filters and by its record name (60 rows); both runs deleted; not run: a caller naming another user, a user with fewer rights (the product's tests)
---
## What you build
From POS build 2.0.0.654, your service calls `/api/method/ivendnext_mpos.api.v1.run_report` with the report's name and its filters, as Desk runs it, and reads the columns and rows. A report iVendNext prepares in the background is queued with `prepare_report` and read when its run is done (`recipes/shop_reports.md`).

## Limits
- A prepared report is never started by `run_report`: it answers the last finished run for those filters, or nothing. Queue a run once, then poll it.
- `run_report` reads **as the user the call names** (`user`), not only as your service's user, and a named run is read whole by its record name. Never pass a user or a run name iVendNext did not choose.
- `prepare_report` checks no right: any signed-in user may queue any report, and reads its output filtered only by their own User Permissions.
- What a report shows depends on the key's user: a branch user's stock reports are fenced by some reports, not all (the card *branch-sees-own-stock*).

## Tell the customer
Our service reads your own reports as the user you give it, and as any user a call names; a background run named by its record is read whole, whoever made it; and any signed-in user may queue a background report and read its output. Give our user only the reports and stores it needs.
