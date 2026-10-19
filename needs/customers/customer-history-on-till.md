---
id: customer-history-on-till
title: A customer's recent visits on the till
area: customers
topic: history-and-crm
asks: A customer's shopping history or trend on the till: recent visits, the store, who served and the discount on each
status: ready-with-limits
door: partner-page
blocked-by: -
recipe: recipes/customer_history_page.md
sample: samples/s28_merge_and_history
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.648 · the sample's page with the context the shop signed in Desk: three sales by three people, each discount, the roll-up skipped, no sales, a reused context refused; not run: the till's own key and card (no till sign-in)
---
## What you build
A partner page, opened by a till key with the customer on the sale (or in Desk for a customer); your server reads the sales over the record API and shows who served and the discount on each.

## Limits
- The till's own customer card already shows, read from the code at the pinned build and not run on a site: name, phone, e-mail, member since, credit limit and balance, lifetime spend, visits, what they buy, loyalty and the last 10 sales, each with its number, date, first item, store, amount, whether a return and its mode.
- It does not show who served or the discount on each sale: your page adds them, read from the sale records (run on a sandbox).
- The sales come from till sales and non-consolidated Desk sales; the day's roll-up invoice is skipped, or each sale shows twice (Desk sales and a hand-made roll-up run on a sandbox; till sales and a roll-up made by a till's closing: laptop only).
- Online only; the cashier presses the key; a customer and an item must be on the sale. A default walk-in customer on every sale opens the page for the walk-in.
- The app's key reads every sale and every user's full name; the built-in Administrator's name is not readable (run).

## Tell the customer
The cashier sees a customer's recent visits, with who served and each discount, on a page opened by a key on the till; it needs a connection.
