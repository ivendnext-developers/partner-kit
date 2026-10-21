---
id: settings-drive-rules
title: One settings page that drives the shop's rules
area: setup
topic: roles-and-data-rules
asks: Change the limits and who is told in one settings page, not in each rule
status: ready-with-limits
door: event-feed
blocked-by: -
recipe: recipes/event_feed.md
sample: samples/s22_customer_loyalty
request: -
verified: laptop 2026-10-16 · S22's settings_sync, 2 tests · not run on a shop
---
## What you build
A settings record of your own (named `Default`); when it is saved, your service copies its values into the save rules' limits and the notifications' recipients it names. Recipe section *A settings record that drives rules*; S22's `settings_sync` (a standalone, tested function S22 itself does not call).

## Limits
- For the seconds between the settings save and the copy, the rules hold the old values.
- From POS build 2.0.0.654 a save rule can read its limit and its role from a settings record itself (`value_from_type`, `contracts/pages/save_rules.md`), with no copy and no delay; this route remains for a notification's recipients and for an older build.
- Not run on a shop.

## Tell the customer
The limits and the people told are changed in one settings page, and the rules follow within seconds.
