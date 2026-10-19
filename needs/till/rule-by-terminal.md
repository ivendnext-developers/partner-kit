---
id: rule-by-terminal
title: A rule that depends on which terminal the sale is on
area: till
topic: till-screen
asks: A rule that depends on which terminal the sale is on, beyond its POS profile
status: not-yet
door: request
blocked-by: extension-point
recipe: none
sample: none
request: P-CAPTURE2
verified: carried 2026-10-16 · not re-run
---
## What you build
Nothing yet: the check before payment does not name the terminal today. The extension point asked for adds it.

## Limits
- Today a rule can depend on the sale's POS profile, not on the terminal.

## Tell the customer
A rule per terminal is not possible yet; per POS profile it is. We have asked for it.
