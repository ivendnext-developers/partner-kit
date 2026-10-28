---
id: shelf-labels-from-till
title: Shelf and item labels printed from the till
area: documents
topic: layouts-and-labels
asks: Print shelf labels from the till
status: ready-with-limits
door: label-layout
blocked-by: -
recipe: contracts/pages/label_layout.md
sample: none
request: -
verified: carried 2026-10-16 · not re-run
---
## What you build
A label layout the retailer declares or your manifest installs (HTML, or Zebra printer commands); the till prints it from an item's card or a basket line, on any printer the device reaches. From POS version 2.1.0 it may print up to three of the item's own fields, `{item.<fieldname>}` (a strength, a route, an allergen list), and one detail typed on the basket line, `{detail.<attribute>}` (a dispensing label's dose): the label layout page.

## Limits
- Labels from the back office and from Handheld print through a desktop utility.
- At most three item fields, each a Data, Select, Int or Check field every role reads (never a money field), and one line detail; a fourth field, a second detail or a field only some roles read is refused when the layout is saved.
- A field changed or limited to some roles after the layout was saved prints nothing in its place; a line detail prints nothing on a label from the item's card or when the line has none typed.

## Tell the customer
Stores print labels from the till; the back office uses the desktop utility.
