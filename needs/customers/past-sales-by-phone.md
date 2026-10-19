---
id: past-sales-by-phone
title: A customer's past sales, found by their phone number
area: customers
topic: history-and-crm
asks: Find what a customer bought before by typing their phone number
status: ready-with-limits
door: partner-page
blocked-by: -
recipe: recipes/customer_history_page.md
sample: samples/s28_merge_and_history
request: -
verified: read 2026-10-16 at POS 3a2335e0a (the till's search, `returns.py`) · not run
---
## What you build
Two routes that exist today. At the till, the no-receipt return search takes a phone number in any written form and lists that customer's recent sales in the stores it reaches. For more than the till shows (who served, each discount), the customer-history page of sample S28, opened by a till key or from the customer in Desk.

## Limits
- The till's search is the elevated no-receipt lookup: it needs the elevated right or a manager's approval, so it is not every cashier's screen.
- The till's search looks back 30 days and lists up to 200 customers' matches (`LOOKUP_WINDOW_DAYS`, `LOOKUP_MATCH_CAP` in the product's `returns.py`); it is for a return, not a general search screen. Read in the code, not run.
- S28's page needs a connection and a customer on the sale (or open in Desk); see the card customer-history-on-till for its limits.

## Tell the customer
A manager or a cashier with the right finds a customer's recent sales by phone at the till, and a key opens a page with the longer history.
