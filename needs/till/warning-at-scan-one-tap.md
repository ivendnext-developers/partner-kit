---
id: warning-at-scan-one-tap
title: A warning at the scan that the cashier taps past
area: till
topic: questions-during-the-sale
asks: A warning when an item is scanned (another batch has less shelf life), with the cashier tapping to carry on
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/capture.md
sample: samples/s20_capture
request: -
verified: read 2026-10-16 in recipes/capture.md and the capture contract · a confirm on a till not run
---
## What you build
A capture on scan. Your service looks up the item's other batches in the store over the record API, then answers `confirm` with your sentence ("This item has a batch with less shelf life in the store. Add it anyway?"). The cashier taps *Yes* once and the item is added.

## Limits
- It is a question: one tap, and *No* leaves the item off. From POS build 2.0.0.654 the answer may be a notice instead: the sentence shows for 8 seconds and the item is added with no tap (sample S23, *Warn on a shorter shelf life*). An older build refuses a notice and applies your down answer.
- The call is made before the line is added, and an ordinary item scan carries no batch: you can say the item has shorter-dated batches, not that this lot is the longer one, unless the scanned code names the batch. The lot is chosen later, at the batch pick (card first-expiry-first-out).
- Online, your service answers. When it is down or offline, the answer you declared applies (`allow_and_flag` lets the line on and flags it for review), so the warning is missed then.
- Your service reads other batches over the record API: allow for the seconds it takes (the scan waits up to the time you declared).
- Not run: a `confirm` answer on a till.

## Tell the customer
Scanning an item with a shorter-dated batch in the store makes the till ask the cashier once, and one tap adds the item.
