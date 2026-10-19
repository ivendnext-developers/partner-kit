---
id: member-rate-with-promotion
title: A discount the promotions cannot express
area: prices
topic: member-prices
asks: A member rate that multiplies with a promotion, taken after it
status: ready-with-limits
door: sandboxed-function
blocked-by: -
recipe: tools/wasm_kit/README.md
sample: tools/wasm_kit/template
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
Your sandboxed module takes money off a line after every promotion, on the server and on the till offline.

## Limits
- Installing the certified module on a shop, step by step: recipes/configure_no_code.md, *A member rate after the promotions*.
- It runs only once CitiXsys has certified your module, the shop's administrator has added it in Desk, and the shop has raised its limit above 0.
- It is never offered a line a pricing rule has already priced, a return or a gift-card line.
- The Desk POS does not run it: a sale rung there is priced without your module.
- A function that runs on a till is compiled from Rust; one that runs only on the server may be JavaScript.

## Tell the customer
The extra rate is applied after the promotions, on the till too, once our certification and the shop's own limit allow it.
