---
id: manager-approval-cap-per-day
title: No more than so many manager approvals for a discount per store per day
area: till
topic: manager-approvals
asks: No more than so many manager discount approvals per store per day
status: ready-with-limits
door: save-rules
blocked-by: -
recipe: recipes/save_rules.md
sample: samples/s18_rule_guard
request: -
verified: run by the product 2026-10-18 (POS train T12: the eleventh approval refused at the manager's Approve, walked on three frames); not run by a kit sample on a sandbox
---
## What you build
One save rule of kind `count_per_day` on the approval request, from POS build 2.0.0.654: the store's managers may give so many discount approvals a day, and the next is refused when the manager presses **Approve**, in the retailer's words (`contracts/pages/save_rules.md` §8, the worked example; `recipes/save_rules.md`). Sample S18's README carries it.

## Limits
- It counts approvals **given**: one given and never used still counts; one that ran out and was given again counts twice. A sale using an approval never counts it again.
- Approvals given offline are not counted.
- An *Action* request, the record an action approved in person leaves after it ran, is only flagged, never refused. A count rule never sits on a sale or the day close.
- The request's store is the register's POS Profile's warehouse, so a store with several registers has one count.
- A partner's own count of the approvals its check before payment asks for stays a route (sample S23), and is answered at Pay.

## Tell the customer
After the day's limit, a manager's further discount approval for that store is refused at Approve with our sentence, and the cashier sells at the normal price; approvals given offline are not counted.
