---
id: submit-cancel-by-role-when-value
title: Only some roles may submit or cancel when a field holds a value
area: documents
topic: approvals
asks: Only the receiving store receives a transfer; only a supervisor cancels it
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: recipes/save_rules.md
sample: none
request: P-RULES2
verified: run on a sandbox 2026-10-21 · POS 2.0.0.656 (a purchase request's submit refused without the role, submitted with it)
---
## What you build
A save rule of kind *role for action*: the submit, or the cancel, of a record type is taken only by a person holding one of the roles you name, when the record's fields hold the values you name. It holds from Desk, an import and the API. The recipe's manifest installs one.

## Limits
- The conditions read the document's own fields, never its rows: a transfer's rows keep the store each names, so make the header name the store with a *required when* rule.
- The site's Administrator holds every role, so it can always submit and cancel.
- A submit or cancel the till's own work makes (a sale, the day close, a layaway's forfeit, the quote edit and cancel) is flagged, never refused.
- At most 3 conditions.

## Tell the customer
Only the people you name may submit, or cancel, a document that meets your condition; anyone else is refused, in Desk and through an import or the API.
