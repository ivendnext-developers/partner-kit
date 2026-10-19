---
id: derived-price-list
title: A price list worked out from another
area: prices
topic: price-lists
asks: A selling price list worked out from another (a multiple of the buying list, wholesale as a share of retail) and kept in step
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/derived_price_lists.md
sample: samples/s26_derived_prices
request: -
verified: run on a sandbox 2026-10-16 · POS 2.0.0.648 · a source change followed in 14 s, the shop's pricer read the new price, a person's price held, a deleted source ended its row in 15 s, reconcile 0
---
## What you build
An outside app follows price changes on the event feed and writes the derived list's item prices through the record API, by a rule the shop keeps: a factor, an offset, a rounding step and a floor.

## Limits
- The new price arrives seconds after the source is saved (14 seconds on a sandbox; about a minute at worst when the shop's background worker is busy, chapter 5); a sale in those seconds is priced at the old one, and a till takes the new price at its next sync.
- A price a person set on the derived list, or changed there after the app wrote it, is kept and listed, never overwritten; a list that already has prices keeps them, so derive into a new list or end those prices first.
- Only prices for everyone are derived: a price for one customer, one supplier or one batch is left alone.
- Both lists are in one currency, and one list is written by one rule; a loop of lists is refused.
- A promotion or a member discount still applies on top, as always.
- Run one copy of the app per shop.
- The price list record has no formula field (read on a sandbox), and a selling pricing rule is refused (chapter 4), so this is an app, not a setting.

## Tell the customer
The derived list follows its source within seconds of each change (about a minute at worst on a busy shop), by the formula, rounding and floor you choose; a price someone sets by hand on it is kept, and the nightly check lists it.
