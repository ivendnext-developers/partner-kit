---
id: balance-by-day-opening-closing
title: A balance report with opening and closing figures
area: reports
topic: scheduled-jobs
asks: A report of each member's cash balance for any dates, with the opening and the closing figure
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/customer_owned_loyalty.md
sample: samples/s22_customer_loyalty
request: -
verified: laptop 2026-10-16 · S22's daily_balances, 2 tests · not run on a shop
---
## What you build
Your service's daily job writes one balance row per member per day (opening, change, closing) into a record type of your own; a Report Builder report over the rows, filtered by date, reads the opening of the first day and the closing of the last. Recipe step 7 of the loyalty recipe; S22's `daily_balances`.

## Limits
- The closing is taken when the job runs, so a move made between midnight and the run counts in the day that ended.
- A day the job did not run has no row; the next row's opening still follows from the last closing.
- Not run on a shop.

## Tell the customer
Each member's balance is kept day by day, so a report for any dates shows what they started and ended with.
