---
id: question-on-flagged-scan
title: A beep and a question when a flagged item is scanned
area: till
topic: questions-during-the-sale
asks: A beep and a yes-or-no question when the cashier scans an item we flagged
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/capture.md
sample: samples/s20_capture
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
Your service is asked when an item your filter names is scanned; it answers with a beep and a question, a refusal, or values for the line.

## Limits
- Online, your service answers. Offline, the answer you declared applies to the items ticked at the start of the day.
- From POS build 2.0.0.654 your service may answer a notice instead: the item goes on with no tap and your sentence shows for 8 seconds (`recipes/capture.md`, step 6b). Something that must stop the cashier stays a question.

## Tell the customer
Scanning a flagged item makes the till beep and ask the cashier your question before the line is added.
