---
id: price-list-with-photos
title: A price list with a photo for each item
area: prices
topic: price-lists
asks: A price list as a document with a photo for each item
status: ready-with-limits
door: manifest
blocked-by: -
recipe: contracts/pages/print_template_readers.md, recipes/print_pack.md
sample: samples/s29_print_pack
request: -
verified: run on a sandbox 2026-10-21 · POS 2.0.0.658 · a manifest's print format on the price list printed all 21 of its prices, and the photo of the one item given a photo, through ivn_rows and ivn_value; not run: a viewer with fewer rights, a list of 500+ items; the outside program (S29) run on a sandbox 2026-10-16
---
## What you build
A print format on *Price List* in your manifest that lists the list's prices through `ivn_rows("Item Price", …)` and each item's photo through `ivn_value("Item", name=…, field="image")`, with the rights of the person printing:

```jinja
{% for r in ivn_rows("Item Price", filters={"price_list": doc.name}, fields=["item_code", "item_name", "price_list_rate", "uom"], order_by="item_code asc", limit=200) %}
{% set photo = ivn_value("Item", name=r.item_code, field="image") %}
<tr><td>{% if photo %}<img src="{{ photo }}" style="height:60px">{% endif %}</td><td>{{ r.item_code }}</td><td>{{ r.item_name }}</td><td>{{ r.price_list_rate }} / {{ r.uom }}</td></tr>
{% endfor %}
```

For a file made on demand (a spreadsheet as well, or one list per distributor), the outside program of S29 does it instead.

## Limits
- Up to 200 rows a call: a longer list takes more calls (`start` 0, 200, 400), or one print per item group.
- The print shows what the person printing may read; a print sent from the e-mail queue or a background print shows no rows.
- Photos must be kept in the shop, on the item's Image field; an item with none prints without one.
- Every Item Price row of the list prints: one made for a customer or a batch, one past its valid dates, and a disabled item's. For the general list add `"customer": ["is", "not set"]` and `"batch_no": ["is", "not set"]` to the filters (not run), and keep expired prices and disabled items off the list.

## Tell the customer
The shop prints each price list with a photo of each item, from its own prices and images, from the price list in Desk.
