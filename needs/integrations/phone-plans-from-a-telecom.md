---
id: phone-plans-from-a-telecom
title: Mobile plans from a telecom company sold with the phone
area: integrations
topic: outside-systems
asks: Sell mobile plans from our telecom company with the phone: show the plans and prices, confirm at Pay, activate after payment
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/point_handler.md
sample: samples/s52_phone_plans
request: -
verified: bench 2026-10-28 run pp-20261028T170105Z-24298 (installed; Plans pressed; a plan confirmed at Pay and booked; refusals; the activation written from the feed) · laptop tests
---
## What you build
A till key that shows the telecom company's plans for the phone on the sale, plan items priced from a price list your service keeps in step with the telecom company, a check at Pay that confirms the plan and its price for the customer, and an activation after payment from the event feed, its number written to a record listed under the sale. Each retailer keeps its own telecom account in its own iVendNext.

## Limits
- The plan is an item the cashier adds: no till door adds a priced line by itself.
- A price the telecom company changes reaches the price list on the next pass; a sale rung in between is refused at Pay with the new price.
- When your service is down or the till is offline, the check's down answer applies to every sale on that till: S52's lets sales go on, flagged for review.
- A return is not sent to the telecom company: cancelling a plan is its own process.
- The activation number is in a record of your app's (the PP TEL Activation list, by sale), linked to the sale, not a field of the sale.
- One price list per retailer: every till that sells plans sells from it.

## Tell the customer
The cashier sees your telecom company's plans and prices for the phone being sold, the plan is confirmed with the telecom company before the customer pays, and it is activated within a minute of payment, its number kept on a record linked to the sale.
