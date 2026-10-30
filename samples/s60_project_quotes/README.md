# S60 — Project quotes and staged deliveries (`pp_pqt`)

*Start from this sample: `python3 tools/manifest/start.py s60_project_quotes --prefix "ACME PQT"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

A hardware or DIY store's **builder projects**, kept in iVendNext Desk. A builder buys for a job (a house, an extension, a store fit-out): the store quotes the job's materials, the builder takes all or part of the quote, and the goods go to site as the work reaches each stage, often over months and several orders. iVendNext already quotes, orders, takes deposits and delivers an order in parts, at the till and in Desk; what nothing holds is **the builder's project**. This sample adds it: one record per job, a **Project** field on the quote, the order, each delivery, the invoice and the till's documents, a **Stage** on each line, and a **project sheet** that lists the job's documents together. The app moves no money and no stock, and calls nothing outside: no service, no outside address. The [recipe](../../recipes/project_quotes.md) walks a store through it.

It uses the manifest's `doctypes` (a record type and a child table), `custom_fields` (the project on five documents, the stage on three line tables), `print_formats` (the project sheet, reading the documents with `ivn_rows`), `links` and a `documentation` property setter. **When to use it:** a store sells to builders or contractors whose jobs run over several quotes, orders and deliveries, and today it keeps the job on paper or in the builder's purchase order numbers.

## What happens

1. **The project.** The trade desk opens **PP PQT Project** in Desk, **+ Add**: the **Project** as the builder names it (*Oak Street extension*), the **Builder** (a customer; the builder's name shows beside it, read only), the **Store** that serves it, **Started on** and **Finish by**, the **Site address**, **Site contact** and **Site phone**, and the **Stages planned**: a row per stage with the date it is **Wanted on site by** and **What goes** (*Foundations, blocks and cement*; *Frame, timber*). Save: the project is numbered `PQT-00001` and is **Open**.
2. **The quote.** In Desk, a **Quotation** to the builder: choose the **Project**, and on each line type its **Stage** (*Foundations*, *Frame*). The builder accepts all or part of it.
3. **The order.** On the quote, **Create › Sales Order**: Desk's own Create carries the project and every line's stage to the order. Give each line its own **Delivery Date** (the stage's date); the order's date is the last of them.
4. **Staged deliveries.** When the first stage is due, on the order **Create › Delivery Note** and choose the delivery date: Desk takes only the lines due by then, with the project and their stage. The order reads *partly delivered*. The next stage's delivery takes the lines still owed. Each delivery's own **Create › Sales Invoice** carries the project too.
5. **The till.** A quote, an order or a sale made at the till for the builder: open it in Desk (it is a *POS Invoice*) and choose its **Project**; the field can be set after the document is booked. A till order's Sales Order does not carry it: choose the project there too, and every delivery and invoice Desk makes from that order carries it.
6. **The job in one place.** On the project, **Print › PP PQT Project sheet**: the stages planned, then the project's quotes, the till's documents, its orders with the share delivered, its deliveries and its invoices with what is still owed, each as the person printing may read them. Every document list (Quotation, Sales Order, Delivery Note, Sales Invoice, POS Invoice) filters by **Project**; the builder's projects show under the customer.
7. **Done.** Set the project's **Status** to *Completed* (or *Cancelled*). A project is never deleted by the store.

## What the retailer does

Nothing is required. Give the trade desk **Sales User** (or a role of your own with the same rights on the project): they keep projects, quotes and orders and name each document's project. Whoever sends goods out holds **Stock User**, which reads projects; accounts hold **Accounts User**, which reads them. A **Sales Manager** keeps projects too; neither deletes one; a System Manager can. To see the deliveries still to come line by line, open the Sales Order list's **Report** view, filter **Project** and **% Delivered** under 100, add the item columns *Stage*, *Delivery Date*, *Quantity* and *Delivered Qty*, and save it as your own report.

## The files

| File | What |
|---|---|
| `manifest.json` | the project (`PP PQT Project`) and its stage table (`PP PQT Stage`); the field *Project* on Quotation, Sales Order, Delivery Note, Sales Invoice and POS Invoice; the field *Stage* on the quote's, the order's and the delivery's lines; the project sheet; the builder's projects under Customer; the project's help address |
| `tests/test_manifest.py` | the manifest passes the kit's checker and nothing the retailer's install refuses; no outside address, no money field and no rule of its own; the project field one optional Link of one name on the five documents, never `no_copy`, settable after submit; the stage field one optional text field of one name on the three line tables, settable after submit on an order's line, beside its delivery date; the builder required and its name a read-only copy; no table required; the sheet reads each document type with `ivn_rows` filtered on the project, never the framework's own readers, and places the letter head; the Connections; the rights; the help |
| `tests/canaries.py` | each test goes RED when the rule it guards is broken |

## Run it

The tests need nothing but Python:

```bash
python3 -m unittest discover -s samples/s60_project_quotes/tests -p 'test_*.py'
python3 samples/s60_project_quotes/tests/canaries.py
```

Install the manifest in a retailer's iVendNext through **Extension Packages** (guide chapter 3), then open **PP PQT Project**.

## What is refused, and why

- **Connections from the project to its quotes, orders and deliveries**: a manifest's link may only list its own records under a retailer's record. The documents name the project; each list filters by it, and the project sheet lists them all.
- **A report of the deliveries to come, shipped in the manifest**: the retailer's site checks a report against its record type before the install, so a report cannot name a field the same manifest adds to the Sales Order. The sheet shows each order's share delivered; the line view is a report the retailer saves (above).
- **A money field on the project** (a budget, a retention): the quotes, orders and invoices hold the money; a project's budget is a version of your own.
- **A required table**: Desk drops a row whose list fields are all blank, so *no stages planned yet* is a project with no rows.
- **The ERP's own Project**: iVendNext hides that module and its roles, which bring timesheets and tasks, and a quote has no field for it.

## Make it your own

What a partner usually changes:
- **at the till:** naming the project on the till itself, with a till key or a sale detail (recipe [A till key](../../recipes/point_handler.md));
- **money:** a project budget against what was invoiced, retentions, progress claims;
- **pricing:** a builder's own prices per project (iVendNext's price lists and pricing rules per customer already do most of it);
- **delivery:** each stage's delivery booked to the site address and a delivery slot, or a delivery run;
- **the prefix:** `tools/manifest/rename.py` makes your copy under your own reserved prefix in one step (the naming series `PQT-` too: change it in the project's `autoname`);
- **its records:** `tools/deploy/copy_records.py` moves projects between a test site and the retailer's iVendNext.

## Technical notes

### Why it is built this way

A manifest only. iVendNext keeps the quotes and their validity, the orders and their deposits, the deliveries in parts by each line's date, and the invoices; what nothing a retailer sees holds is the builder's job. Desk's own Create copies a field of the same name from the quote to the order, from the order to each delivery and from a delivery to its invoice (header and lines, unless the field is marked not to be copied), so one field name on every document carries the project down the whole chain with no code. The project sheet reads the documents with `ivn_rows`, which applies the person's own rights. With no service there is nothing to host, no key to keep and no user to add.

### Bounds, stated

- **A till order's Sales Order does not carry the project**: the till makes it with a fixed list of fields. Name the project on that Sales Order in Desk; a delivery or invoice made from it in Desk then carries it.
- **The project on a document is not checked against its customer**: the trade desk chooses the builder's project; the builder's projects show under the customer, and the sheet prints each document.
- **The sheet lists what the person printing may read**: a Stock User sees the orders and deliveries but not the quotes and invoices if their role does not read them; a print sent from the e-mail queue lists none (it still prints).
- **Desk shows the records with the prefix** (*IVENDNEXT PQT Project* in the library app).
- **The builder's details are the retailer's**, kept as it keeps its customers; uninstalling the app removes the projects (its export keeps a copy) and the Project and Stage fields from every document.
