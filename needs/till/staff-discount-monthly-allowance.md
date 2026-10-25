---
id: staff-discount-monthly-allowance
title: A staff discount with a monthly allowance
area: till
topic: limits-on-a-sale
asks: Staff buy at the till at a staff rate, and each may take only so much discount a month
status: ready-with-limits
door: configure
blocked-by: -
recipe: none
sample: none
request: -
verified: carried 2026-10-25 · not re-run (read in the POS app's code)
related: manager-approval-cap-per-day, coupon-or-loyalty-cap
---
## What you build
Settings in iVendNext Desk, no app. In **Retail Setting**: *Employee Discount (%)*, the staff rate, and *Employee Monthly Allowance*, the most discount each staff member may take in a month (0 turns the limit off). On each staff member's own customer record tick *Is Staff (POS Employee Discount)* and fill their *Staff ID*. Tick *Excluded From Staff Rate* on an item group that never takes it. Tick *May Apply Employee Discount* on the Retail Permission of the cashiers who may apply it. At the till the cashier attaches the staff member's customer record and applies the staff rate; the till shows what is left of the month.

## Limits
- One staff rate and one monthly allowance for every staff member; an allowance per grade or per person is a request to us.
- Past the allowance the staff rate stops: the rest of the sale is at full price, and the line where it runs out takes part of it. The sale is never refused.
- The staff rate never stacks on a line a promotion or a markdown already prices lower, and never applies to a gift card. A price the cashier types below the list takes the staff rate off that price.
- The month is the calendar month. It counts the staff rate given on booked till sales: a cancelled sale gives it back, a return does not, and a parked sale counts once it is paid.

## Tell the customer
Your staff buy at the till at their staff rate until their monthly allowance is spent; after that they pay full price, and the till shows what is left.
