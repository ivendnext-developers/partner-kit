---
id: own-records-in-desk
title: Your own records in iVendNext Desk
area: documents
topic: own-records-and-fields
asks: Keep our own records, such as a warranty register, in iVendNext with their own screens and print formats
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/manifest.md
sample: samples/s2_bins
request: -
verified: carried 2026-10-15 · not re-run
---
## What you build
A manifest declares your record types, fields, print formats, notifications and workspaces, with native screens; they can be listed under ours.

## Limits
- From POS build 2.0.0.654 a manifest may carry a multi-select field and a settings record of its own (one record, no list) (`guide/07_manifests.md`). Before that build, a settings record is an ordinary record type read by name (the record named `Default`, sample S22).

## Tell the customer
Your records live in iVendNext Desk, with their own screens, lists and reports.
