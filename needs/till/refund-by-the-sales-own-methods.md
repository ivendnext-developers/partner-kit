---
id: refund-by-the-sales-own-methods
title: Refunds back by the methods that paid the sale
area: till
topic: cash-voids-returns
asks: A sale paid by card refunded to the card, never in cash; a return without its receipt only to store credit
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/refund_rules.md
sample: samples/s51_refund_rules
request: -
verified: run on our test bench 2026-10-24 · the check's answer for a sale's return and a no-receipt return; the refund door refusing an excluded method (Store Credit) and paying a kept one
popular: yes
---
## What you build
A settings record and a service that answers the check on every refund the till pays: it takes off every offered method that did not pay the sale being refunded (`return_of.paid_by`), other than the store credit method and any the retailer always allows; and it keeps a return without its sale to the methods the retailer names and the store credit method. Each store refunding only its own sales is a setting, not this app: leave *Use inter-store transactions* off in Retail Setting.

## Limits
- Methods, never amounts: the cashier splits the refund between the methods kept.
- The store credit method is never taken off, or every exchange is refused.
- At a till with a cash drawer, an exchange whose replacement costs less pays its difference in cash: refused when the rule leaves cash out.
- A sale's Pay is never judged.
- Offline the check is not called. A return sent to a register, or a refund made in Desk, is not checked.
- The methods kept must be Allowed in Returns on the POS Profile.

## Tell the customer
A refund goes back the way the customer paid: the till offers only the sale's own methods and your store credit, and a return without its receipt is no way round it.
