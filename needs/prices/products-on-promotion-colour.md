---
id: products-on-promotion-colour
title: A coloured row for products on promotion in the Desk list
area: prices
topic: promotions
asks: A coloured row in the Desk product list for the products on promotion
status: ready-with-limits
door: manifest
blocked-by: -
recipe: contracts/pages/list_mark.md
sample: none
request: -
verified: run on a sandbox 2026-10-21 · POS 2.0.0.658 · a manifest's list mark installed switched off, switched on, reached the Desk page's boot data for the user (and one ticked item matched its conditions), gone again when switched off, uninstalled; not run: the label drawn on a screen (walked by the product)
---
## What you build
A manifest with a tick-box field of your own on Item and one list mark on it: Desk shows *On promotion* in green on each product row where the tick is on. These are the field and the mark that ran on the sandbox (`pp_plm`, a placeholder prefix: use your own).

```json
"custom_fields": [{"dt": "Item", "fieldname": "pp_plm_on_promotion", "fieldtype": "Check", "label": "On promotion", "insert_after": "disabled"}],
"list_marks": [{"record_type": "Item", "label": "On promotion", "colour": "green", "sequence": 10,
  "conditions": [{"field": "pp_plm_on_promotion", "operator": "=", "value": "1"}, {"field": "disabled", "operator": "=", "value": "0"}]}]
```

The retailer ticks the field on the products on promotion (or your service does, over the record API), and switches the mark on in **Retail List Mark**.

## Limits
- A label, not a row colour: Desk colours the row's label, and also shows it in the form's header.
- Not on a submitted record type or one with an active workflow; at most five marks per record type.
- It shows after the record type's own document states and before its own list labels; `disabled = 0` keeps *Disabled* on a disabled item.
- A user who may not read every field the mark reads never sees it, and the report view shows no label.

## Tell the customer
The product list shows *On promotion* in green on each product on promotion; it changes nothing else.
