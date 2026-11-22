---
id: erp-sap-business-one
title: An ERP on SAP Business One
area: integrations
topic: erp
asks: Our SAP Business One receives sales, returns and stock transfers, and keeps customers, products, warehouses and price lists in step
status: ready-with-limits
door: our-connector
blocked-by: -
recipe: guide/10_integrations.md
sample: none
request: -
verified: 2026-11-22 · read from the App library's SAP Business One card; not run on a site for this card
---
## What you build
Our SAP Business One connector, an App library app sold by key. It keeps customers, suppliers, products, price lists and warehouses in step between iVendNext and SAP Business One, and posts the stores' sales, returns and stock transfers to it; every sync shows in the connector's monitor, where a failed one is kept and can be retried. You add it to the site with its key.

## Limits
- Set it up on a fresh site: the first load takes master data from SAP Business One, so it comes before the customer's own customers, items and warehouses.
- A store's warehouse needs a cash customer whose name is 15 characters or fewer (SAP Business One limits that code).
- The customer's SAP administrator installs our add-on in SAP, makes the SAP user for it and opens five stock tables to queries in the Service Layer.
- A connector licence is needed. The sales and stock go to the customer's own SAP Business One server, at the address it enters.
- One ERP per company.

## Tell the customer
Our connector keeps your SAP Business One in step with your stores and books their sales into it; your SAP administrator installs our add-on first, and it is set up on a fresh site.
