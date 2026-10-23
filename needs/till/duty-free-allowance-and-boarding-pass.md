---
id: duty-free-allowance-and-boarding-pass
title: A boarding pass on every airport sale, and each passenger's duty-free allowance
area: till
topic: limits-on-a-sale
asks: Our airport stores sell only to passengers with today's boarding pass, and only up to each passenger's allowance
status: ready-with-limits
door: check-before-payment
blocked-by: -
recipe: recipes/duty_free_allowance.md
sample: samples/s36_duty_free
request: -
verified: 2026-10-22 · bench
---
## What you build
A sale detail for the boarding pass, which the cashier scans in, and a service that answers the check before payment at the airport stores' tills. It reads IATA's bar-coded pass: the flight must leave from (or arrive at) the retailer's airport, dated the airport's today or tomorrow (arriving: today or the two days before). It adds up each item group with a duty-free allowance, this sale and the passenger's earlier sales on the same pass, in the group's own measure (litres, cigarettes).

## Limits
- Answered when the cashier presses Pay, not when the pass is scanned.
- The pass goes in through Sale details by a keyboard scanner or typing; a phone's camera does not fill it yet.
- The till keeps 140 characters of a sale detail: a phone pass with its security part is cut, and every leg that fits whole is read (the first always is; a connecting passenger shows the pass of the flight that leaves here).
- A departing flight delayed past midnight is refused after midnight as another day's.
- Offline, the till does not ask the service: the sale goes on and is flagged when it syncs.
- Earlier sales are counted at the check: two sales on one pass checked at the same moment at two tills each miss the other. Sales at another retailer are not seen.
- The app's user needs a plain read on the retailer's sales and no User Permissions, or earlier sales are only partly seen and a passenger can buy past the allowance.
- Passenger categories (transit, crew, airport staff) and their tax are not judged.
- The check does not run on a park to a till, a layaway deposit, an account collection or the Desk's own POS screen.

## Tell the customer
Each airport sale carries the passenger's boarding pass, and a sale over a passenger's allowance is refused at Pay with the reason.
