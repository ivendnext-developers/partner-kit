---
id: no-duplicate-customer-by-phone
title: No second customer with the same phone number
area: customers
topic: customer-records
asks: A cashier creating a customer whose mobile number is already on another one gets the existing customer, not a duplicate
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/save_rules.md
sample: none
request: -
verified: carried 2026-10-25 · not re-run (read in the POS app's code)
related: unique-across-records
---
## What you build
At the till, nothing: when the cashier adds a new customer, a phone number already on an enabled customer attaches that customer instead of making a second one. The till compares digits only, reading a leading 0 with your site's dialling code (on a UAE site, 0501234567 is +971 50 123 4567), and looks in both the till's *Phone Number* and Desk's *Mobile No*. Online it also matches a known e-mail. For customers made in Desk, by an import or over the API, add save rules of kind *unique across* on the customer's *Mobile No* and on its *Phone Number* (card unique-across-records), and a *pattern* rule of shape *international number* if every number must be written the same way.

## Limits
- A save rule compares the number as written, in one field: 0501234567 and +971501234567 are two values to it, and a number in *Mobile No* is not compared with one in *Phone Number*. Use the pattern rule, so every number is written the one way.
- A disabled customer still holds its number for the save rule, while the till skips it when matching: with a rule on *Phone Number*, the till's new customer with that number is then refused.
- Offline, the till matches by phone only. A number written with 00 in front is not matched with one written with +.
- Two people sharing one number: the till always attaches the existing customer, so the second can be made only in Desk, and a save rule refuses it there too. Showing the cashier the customers with that number to choose from is a request to us.

## Tell the customer
A customer is found by their phone number at the till, so a returning customer is not created again; with the save rules set, the back office refuses a second customer with the same number written the same way.
