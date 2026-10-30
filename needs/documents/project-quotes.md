---
id: project-quotes
title: A builder's project across its quotes, orders and staged deliveries
area: documents
topic: own-records-and-fields
asks: One builder's job kept as a project, with its quotes, orders, deliveries in stages and invoices named to it and listed together
status: ready-with-limits
door: manifest
blocked-by: -
recipe: recipes/project_quotes.md
sample: samples/s60_project_quotes
request: -
verified: 2026-10-30 · bench
related: repairs-by-serial
---
## What you build
The builder's project as your manifest's own record type: the builder (a customer), the site, the dates and the stages planned. A Project field of one name on the quote, the order, the delivery, the invoice and the till's documents, and a Stage field of one name on the lines of the quote, the order and the delivery, so Desk's own Create carries both from the quote to every delivery and invoice. A print format, the project sheet, lists the job's documents with the viewer's own rights; each document list filters by project.

## Limits
- The till does not name the project: a till document is named in Desk after it is booked, by a role that changes till documents (Retail Manager, Accounts User), and a till order's Sales Order by the trade desk. Naming it at the till is a version of your own.
- A manifest's Connections cannot list the retailer's documents under the project, and a report it ships cannot name a field it adds to the Sales Order: the sheet and the lists' filter do that work.
- The project holds no money; the quotes, orders and invoices do.

## Tell the customer
Each builder's job is one project: its quotes, orders, deliveries in stages and invoices are named to it and listed together on one sheet, so the counter and the office see where the job stands.
