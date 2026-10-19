---
id: price-list-with-photos
title: A price list with a photo for each item
area: prices
topic: price-lists
asks: A price list as a document with a photo for each item
status: ready-with-limits
door: outside-app
blocked-by: -
recipe: recipes/print_pack.md
sample: samples/s29_print_pack
request: P-TEMPLATEHELPERS
verified: run on a sandbox 2026-10-16 · POS 2.0.0.650 · the sample's program made the page from 21 prices with photos on two items (a missing photo file became a grey box) and it printed to a 3-page A4 PDF; a print format on the item showed its photo in the shop's PDF; not run: a print format listing a price list's rows, a list of 500+ items
---
## What you build
A small outside program makes a page that prints to PDF, and a spreadsheet file, for each distributor from the price list and the items' images (the sample's `catalogue.py`).

## Limits
- Photos must be kept in the shop: attach the file to the item and set its Image field (a PNG, JPEG, GIF or WebP up to 800 kB); any other item gets a grey box and is reported.
- General prices only: a price made for one customer, supplier or batch is skipped, so a list for one distributor is that distributor's general list; disabled items are left out.
- The page is a file made on demand, not a live view: run it again when prices or photos change.
- A print format on the price list is not offered: a kit template cannot read the price rows; ask for P-TEMPLATEHELPERS (readers under an iVendNext name).

## Tell the customer
Each distributor gets a price list with a photo of each item, made by our app from the shop's own prices and images.
