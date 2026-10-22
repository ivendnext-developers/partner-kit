---
id: age-check-at-scan-and-pay
title: An ID check for alcohol, tobacco and other restricted items, at the scan and at Pay
area: till
topic: limits-on-a-sale
asks: Our tills must show the cashier the customer's minimum age on alcohol, tobacco and vapes, and never let one be paid without an ID check
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/age_check.md
sample: samples/s37_age_check
request: -
verified: 2026-10-22 · bench
---
## What you build
An age on each restricted item group (or item), and a service that answers two extension points. At the scan of a restricted item, it shows the date of birth the customer must be born on or before, and one tap records *"18 or over"* on the sale as a sale detail. At Pay, it refuses a restricted line the recorded check does not cover: an item picked from a list, a check refused earlier, or a lower age.

## Limits
- No date of birth or ID number is captured: the sale records the age band the cashier confirmed.
- A sale whose first item is restricted is asked twice (the first scan has no sale reference to remember).
- A later, lower ask can replace a higher one on the sale (one value per sale detail); Pay then names the higher age to enter.
- Offline, or with the service down, the item goes on and the sale is paid, flagged; a shop can make the scan refuse a scanned restricted item, but an item picked from a list still goes on, flagged.
- One scan service per POS Profile: where Till guard rules or Warranty capture answers the scan, only the check at Pay can be switched on. At most three checks per POS Profile, 10 seconds together.
- One time zone and one age per item group for the whole site.
- A notice reaches POS build 2.0.0.654 and later; on an older build the scan's sheet does not show, and the check at Pay still holds.
- No manager's override, no restricted selling hours, no ID scanner.
- A group under a restricted group cannot be made free of age; an age set on a template reaches its variants at Pay, but the scan asks about a variant by its own age or its group.
- The check does not run on a park to a till, a layaway deposit, an account collection or the Desk's own POS screen.

## Tell the customer
The cashier sees the date of birth to check at the scan of a restricted item, and while the app's service answers, a restricted item is not paid without a recorded ID check; otherwise the sale is flagged for review.
