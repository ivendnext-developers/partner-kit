---
id: rule-by-terminal
title: A rule that depends on which terminal the sale is on
area: till
topic: till-screen
asks: A rule that depends on which terminal the sale is on, beyond its POS profile
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/rule_guard.md
sample: samples/s18_rule_guard
request: -
verified: run by the product 2026-10-16 · POS train T11's walk sent the day and the terminal with each check (pos_opening, pos_terminal); not run with a kit sample
---
## What you build
A check before payment that reads the sale's POS day and its terminal (`pos_terminal`), sent with every check, and answers by terminal: one rule per counter without one POS profile per counter.

## Limits
- A day suspended at one terminal and resumed at another moves its terminal mid-sale: the till asks you again before money moves; a sale whose card was already charged, or one synced from offline, is booked and flagged for review instead.
- A shop's consent ticked before its site took the day and the terminal lapses: the check asks nobody until the shop ticks it again.
- A service that validates the request against an older copy of the contract refuses the two new fields: take the kit's current copy.
- No kit sample reads the terminal yet: S18 shows the check, the recipe the request.

## Tell the customer
A rule can differ by terminal, not only by POS profile: the till sends the terminal with every check.
