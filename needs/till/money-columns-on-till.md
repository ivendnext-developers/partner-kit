---
id: money-columns-on-till
title: Show or relabel the discount price or the total including tax on the till
area: till
topic: till-screen
asks: Show or relabel the discount price or the total including tax on the till
status: ready-with-limits
door: field-rules
blocked-by: -
recipe: recipes/field_rules.md
sample: samples/s21_field_rules
request: -
verified: run by the product 2026-10-18 (POS train T12's walk, counter, phone and tablet frames: a List price column and sub-line, the total read Total incl. VAT, the receipt kept its own words); not run by a kit sample on a sandbox
related: till-fields-shown-renamed-hidden
---
## What you build
Two field rules on the till theme, from POS build 2.0.0.654: `cart_line · list_price · show · List price` shows each line's price before any cut, and `totals · grand_total · relabel · Total incl. VAT` gives the total the retailer's word (`recipes/field_rules.md`, *The money words*). The line's price, discount and total and the totals' discount, charges, delivery and tax take a new label too. No figure changes.

## Limits
- The paper keeps its own words (*Total*, *Tax (incl.)*): for the retailer's word on the receipt, name your own print format.
- The label may not hold digits or signs, but a claim in words passes: *Price incl. VAT* is false on a profile whose prices exclude tax. Word a money label for every POS profile the theme serves.
- On an item sold at a cross-sell offer's price, the list price is the offer's base, so that line shows no struck price.
- The customer display, POS Studio's previews, the screens of a sale already made and the charges sheet's heading keep the shipped words.
- A money figure is never hidden, and no figure moves.

## Tell the customer
The till can show each line's list price and call its money columns and totals by your words; the receipt keeps its print format's words unless we give you your own; a label is checked for digits and signs, not for truth, so it must be true on every till it serves; an offer line shows no struck price; the customer display and past sales keep the shipped words.
