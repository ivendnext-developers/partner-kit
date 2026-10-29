---
id: walk-in-mobile-for-marketing
title: A walk-in customer's mobile number kept for marketing
area: customers
topic: customer-records
asks: Walk-in customers have their mobile number captured at the till, so that later marketing can reach them
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/required_sale_details.md
sample: none
request: -
verified: carried 2026-10-29 · not re-run (read in the POS app's code and sample S50's tests)
related: require-new-customer-phone-or-email, no-duplicate-customer-by-phone, required-sale-details-for-some-customers
---
## What you build
Nothing new. **The usual way:** the cashier adds the walk-in as a new customer with a name and the mobile number, and the sale becomes that customer's; a field rule makes the phone required on that sheet (card require-new-customer-phone-or-email). **If every walk-in sale must carry a number:** *Required sale details* from the App library, with a sale detail *Mobile number* and a rule on the walk-in customer's group (recipe required_sale_details, sample S50).

## Limits
- Online, a number already on a customer attaches that customer instead of making a second one (card no-duplicate-customer-by-phone). Offline, the till does not match it: when the sale reaches iVendNext, a number on more than one customer, or on a customer with another name, leaves the sale on the walk-in, flagged for review.
- A walk-in who asks for the receipt by SMS or WhatsApp becomes a customer of their own, from the name and number on the receipt sheet; the sale stays the walk-in's.
- To know who agreed to marketing, add a Select field of your own to Customer, its options a blank line, then Yes and No (a Select with no blank line saves its first option when nothing is chosen), and show it on the new-customer sheet with a field rule. A returning customer found by their number keeps their record as it was: record the answer by editing the customer.
- A rule on a group the walk-in shares with named customers asks them too. Then give each store's walk-in customer (the warehouse's *Cash Customer*) a new group in Desk beside its old one, under the same parent (a group that has customers in it cannot be made a parent), before you write the rule. The till cannot change a walk-in's group.
- The new group takes the rules of the groups above it, not of the group the walk-in left. Set on it what the old group had of its own: pricing rules, tax rules, *Default Price List*, receivable account, payment terms and credit limit. Promotions and coupons name a group exactly: add the new group to every one that excludes the old group, or walk-in sales start taking them. A rule of an App library app written on the old group (coupon rules, payment method rules) is written again on the new group.
- With the rule on, a walk-in who will not give a number cannot be sold to as a walk-in, online and while the service answers: offline, or when the service does not answer in time, the sale goes on and is flagged. If the phone is also required on the new-customer sheet, such a walk-in cannot be added as a customer either. A made-up number gets past the till and fills the list with numbers nobody answers. The sale detail's *RegEx Pattern*, such as `^\+?[0-9]{8,15}$` (a plus, then digits, no spaces), checks its shape at every booking.
- A number kept on a sale is not a customer. Marketing reads it from the sales' details in Desk (POS Invoice, *POS Invoice Sale Attribute*), where the same number on two sales is two values.
- A mobile number is personal data. Ask for the customer's agreement to marketing as your country's law requires.

## Tell the customer
The cashier keeps a walk-in's mobile number as a customer of its own, and the till finds that customer again by the number. If every walk-in sale must carry a number, the till asks for it at Pay in your words.
