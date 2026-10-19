---
id: confirm-setup-on-new-record
title: Initials that confirm a new record is set up, in place of a confirm pop-up
area: documents
topic: checks-on-save
asks: When a new item is first saved, the user confirms that batch and expiry are on and the item is linked to its parent
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: contracts/pages/save_rules.md
sample: none
request: -
verified: read 2026-10-16 at POS save_rules.py (an empty text field is refused, an unticked tick is not) · the manifest passes tools/manifest/validate.py · not run on a shop
---
## What you build
A short text field, *Setup confirmed by*, that your manifest adds to the record (a field you add may be read-only or hidden, never mandatory), and a save rule of kind *required when* on that field, with the conditions that make the confirmation matter (for example, batch tracking is on). The save is refused with your message until the user types their initials, in Desk, an import and the API alike.

## Limits
- Initials, not a tick: the rule counts an empty text field as missing, but it does not count an unticked tick as missing (the tick is 0, which is a value). Do not build it on a tick.
- A field on the form, not a pop-up: your code cannot show a question inside Desk (rule 4). Typed once, it stays, so nothing asks again.
- It holds on every save until filled, not only the first: records saved before the rule existed need the initials at their next save.
- On a till sale and the till close a save rule only flags, never refuses (card required-when-another-filled).
- Not run: the condition on a tick field (batch tracking) was not run on a shop.

## Tell the customer
A new record cannot be saved until someone types their initials to confirm it is set up; there is no pop-up, and it is asked once.
