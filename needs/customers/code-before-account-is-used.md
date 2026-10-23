---
id: code-before-account-is-used
title: A code to the customer's phone before their account is used
area: customers
topic: customer-records
asks: The member reads out a code we text them before their loyalty balance, credit or account can be used at the till
status: ready-with-limits
door: capture-on-event
blocked-by: -
recipe: recipes/customer_code_check.md
sample: samples/s48_customer_code_check
request: -
verified: run on our test bench 2026-10-23 · a code texted through the shop's own SMS settings and Notification, the right code letting the customer on and the payment through, a wrong code refused, the customer with no mobile number taken off
---
## What you build
A capture on *customer select* that answers with a code field. When the cashier puts a customer of a group the shop names on a sale, your service writes a code to a record of its own, and the shop's own Notification texts it to the mobile number on the customer's record. The cashier types the code the customer reads out; until it is right, no door that takes payment takes that customer. The sample S48 does it, one rule per customer group.

## Limits
- The code comes when the customer is picked, not when they pay from their loyalty balance: name the groups that need it.
- The code goes to the number on the customer's record: a cashier who may change that number can send it elsewhere, unless the shop keeps the phone fields for its managers.
- The shop's own SMS settings and a Notification send the text: the kit brings no gateway.
- Never asked for the store's walk-in customer; offline the declared down answer applies.
- One app answers *customer select* on a POS Profile.

## Tell the customer
Before a member's loyalty balance or account can be used at the till, we text them a code and the cashier asks for it, so no one else can spend what is theirs.
