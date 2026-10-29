---
id: minimum-sale-before-loyalty
title: Loyalty points, or another payment method, only from a minimum sale
area: till
topic: payment
asks: Loyalty points redeemed only on a sale of at least a set amount; a payment method offered only from an amount
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/payment_method_rules.md
sample: samples/s46_payment_method_rules
request: -
verified: 2026-10-29 · bench
related: payment-methods-for-sale, coupon-or-loyalty-cap
---
## What you build
Your service answers the check before payment. iVendNext keeps the rule per customer group, and each payment method on it may name an amount, *From a sale of*: below it the method is left out of that sale, with the amount needed; from it the method is offered. Loyalty points pay through the payment method named *Loyalty Points*, so loyalty points only from a sale of 2,000 is one rule on the top customer group: *Every payment method but these*, *Loyalty Points*, from a sale of 2,000.

## Limits
- Answered when the cashier presses Pay. The till's loyalty form still shows when the customer has loyalty points: a redemption below the amount is refused when the payment completes, in your words.
- *Loyalty Points* must be one of the till's payment methods (on the POS Profile or its Payment Template), or the check cannot leave it out.
- On a split, a loyalty leg added after a card leg books and is flagged for review, never refused.
- The Mode of Payment's own minimum amount is the least one payment by that method may be, not the sale's size.
- The sale's total is as rounded for payment, after its discounts, tax included; equal is enough. It is the whole sale's total, not what is left after another method.
- One amount per method per rule, read in each sale's own currency.
- A customer group with a rule of its own adds the same row to it: one rule decides, whole.
- Refunds are not judged. Offline, the till does not ask the service: every method is offered and the sale is flagged when it syncs.

## Tell the customer
On a sale below the amount, the till refuses loyalty points with the amount needed; the customer pays with another method or adds to the sale.
