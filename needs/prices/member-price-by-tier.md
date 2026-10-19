---
id: member-price-by-tier
title: A member price for each customer tier
area: prices
topic: member-prices
asks: Members pay less, by tier
status: ready-with-limits
door: configure
blocked-by: -
recipe: recipes/configure_no_code.md
sample: samples/s5_config_pack
request: -
verified: carried 2026-10-15 · not re-run
popular: yes
---
## What you build
One Customer Group per tier and one promotion per tier; each tier's promotion excludes every other group, non-members included. Works offline for a member on the till's offline customer list.

## Limits
- A promotion cannot be aimed at a group, only exclude groups: a group added later gets every tier's discount until the set-up script (apply_config.py) runs again.
- A customer with no customer group gets the member discount: give every customer a group, and set Selling Settings → Default Customer Group to a non-member group (without it, a customer made at the till can land in a member tier).
- Use lowest-level groups only: a customer in a group that has groups under it is never excluded.
- The member discount is on the whole sale, not on each line, and only one sale-level promotion applies.
- Lines already discounted are left out; a cashier's sale discount replaces the member discount (from the code; not walked).

## Tell the customer
Each tier gets its own price through a promotion; every customer needs a group, and the discount shows on the sale's total.
