# Project quotes and deliveries by stage — the recipe

A hardware or DIY store sells to builders, and a builder buys for a job: the store quotes the job's materials, the builder takes all or part of the quote, and the goods go to site as the work reaches each stage, over months and several orders. iVendNext already quotes (at the till and in Desk, with a validity), turns a quote into an order line by line, takes a deposit, and delivers an order in parts by each line's own date. This recipe adds the one thing nothing holds: **the builder's project**, as the retailer's own record in iVendNext Desk, named on every quote, order, delivery, invoice and till document of the job, with a **stage** on each line and a **project sheet** that lists the job's documents together. It is for an iVendNext Partner, or the CitiXsys Consulting Team, who wants a store's builder jobs out of folders and purchase order numbers without code inside the retailer's iVendNext.

**Reference implementation:** `samples/s60_project_quotes/`.

**When to use it.** The store has trade customers whose jobs run over several quotes, orders and deliveries, and the counter or the office has to find a job's documents one by one today. The quotes, orders, deposits, deliveries in parts and invoices stay iVendNext's own; the ERP's own *Project* sits in a module iVendNext hides, with its roles switched off, and a quote has no field for it.

**The four rules, here.** No code runs inside the retailer's iVendNext. No address is called: the app is a manifest of records, fields, a print format and one Connection. It reads and writes no money and no stock. It sends no message.

## What the store sees

1. **The project.** The trade desk opens **PP PQT Project** in Desk and presses **+ Add**: the **Project** as the builder names it, the **Builder** (a customer; its name shows, read only), the **Store**, **Started on**, **Finish by**, the **Site address**, **Site contact** and **Site phone**, and a row per stage in **Stages planned** (the stage, the date it is **Wanted on site by**, **What goes**). Saved, it is numbered `PQT-00001` and is **Open**.
2. **The quote.** A Desk **Quotation** to the builder names the **Project**; each line names its **Stage**.
3. **The order.** **Create › Sales Order** on the quote: the project and every line's stage come with it. Each line gets its own **Delivery Date**, the stage's date.
4. **Staged deliveries.** **Create › Delivery Note** on the order: Desk asks which delivery dates to send (the dates up to today come ticked); tick the stage's date and press **Select**: only the lines of the ticked dates, with the project and their stage. The next delivery takes the lines of its own date. **Create › Sales Invoice** on a delivery carries the project.
5. **The till's sales and orders.** A sale or an order rung at the till for the builder is a **POS Invoice** in Desk: once it is booked, an **Accounts User** (Sales User reads no till document) opens it from the POS Invoice list and chooses its **Project**. A till quote is not named: name the sale or order it becomes. The trade desk names a till order's own Sales Order.
6. **The job in one place.** **Print › PP PQT Project sheet** on the project: its stages, then its quotes, the till's documents, its orders with the share delivered, its deliveries and its invoices with what is still owed. Every one of those lists filters by **Project**, and the builder's projects show under the customer.

## Projects

The record type `PP PQT Project`, numbered `format:PQT-{#####}`, tracked (its history shows who changed it and when), its title the project's name (shown in place of the number wherever it is chosen):

| Field | What |
|---|---|
| Project (`project_name`, required) | the job as the builder names it |
| Builder (`customer`, required) | a Customer; the **Builder's name** (`customer_name`) is a read-only copy fetched from it |
| Status | *Open*, *Completed* or *Cancelled*; *Open* when made |
| Store, Started on, Finish by | the store that serves the job and its dates |
| Site address, Site contact, Site phone | where the goods go, and who takes them |
| Stages planned (`stages`, the table `PP PQT Stage`, never required) | a row per stage: **Stage**, **Wanted on site by**, **What goes** |
| Notes | anything else |

On the retailer's documents, two fields, each one name everywhere:

| Field | On | What |
|---|---|---|
| Project (`pp_pqt_project`, a Link) | Quotation, Sales Order, Delivery Note, Sales Invoice | the project the document belongs to; never required; settable after submit; a standard filter on each list |
| Project (`pp_pqt_till_project`, a Link) | POS Invoice | the same, for a till sale or order, under a name of its own (below) |
| Stage (`pp_pqt_stage`, text) | the lines of Quotation, Sales Order and Delivery Note | the stage a line goes to site for; on an order's line beside its own delivery date, and settable after submit there |

**Why one name.** Desk's own **Create** (a quote's *Sales Order*, an order's *Delivery Note*, a delivery's *Sales Invoice*) copies every field of the same name from the document it is made from, on the header and on the lines, unless the field is marked not to be copied. One name on every document therefore carries the project and the stages down the whole chain, with no code. The till makes a till order's Sales Order with a fixed list of fields of its own, so that one is named by hand.

**Why the till's field has its own name.** When iVendNext combines the till's sales into Sales Invoices (at once on some sites, at the day's close on others), it copies every field of the same name from each sale (the last one's value wins). A till sale's project under the chain's name would land on that combined invoice, which can hold the builder's other sales of the day, and the sheet would list the builder's other sales of that day under the project. A name of its own keeps it off.

## The project sheet

The print format *PP PQT Project sheet* (Jinja) places the store's **Letter Head** itself (`{% if letter_head and not no_letterhead %}<div class="letter-head">{{ letter_head }}</div>{% endif %}`: only Desk's standard layout adds it on its own), prints the project, the builder, the site and the stages planned, then one section per document type, each read with `ivn_rows` filtered on the project:

```jinja
{% set rows = ivn_rows("Sales Order", filters={"pp_pqt_project": doc.name},
                       fields=["name", "transaction_date", "delivery_date", "grand_total", "per_delivered", "status"],
                       order_by="transaction_date asc", limit=200) %}
```

`ivn_rows` reads with the rights of the person printing ([the readers](../contracts/pages/print_template_readers.md)): a section lists only the documents that person may read, and a print rendered from the e-mail queue or a background job lists none (each section then says *None yet.*, and the sheet still prints). Never read them with the framework's own readers, which skip the viewer's rights: the kit's checker warns, and refuses where `ivn_rows` serves the type.

## Steps

1. **Add the record types above** to your manifest (`doctypes`, the stage table with `"istable": 1`), with no money field: the quotes, orders and invoices hold the money. Never make the stage table `reqd`.
2. **Add the two fields** (`custom_fields`): the project as a Link of one name (your reserved field prefix, then `_project`) on the four documents Desk's Create chains (Quotation, Sales Order, Delivery Note, Sales Invoice) and, under a name of its own (`_till_project`), on POS Invoice, `allow_on_submit` 1, `in_standard_filter` 1, never `reqd`; the stage as a text field of one name on the three line tables, `allow_on_submit` 1 on the order's line, placed after its `delivery_date`.
3. **Add the project sheet** (`print_formats`, above), the builder's projects under Customer (`links`), and a `documentation` property setter that points at your help.
4. **Leave out** a Connections list of the documents under the project (a manifest's link may only list its own records under a retailer's record) and a report on the Sales Order naming your field (the retailer's site checks a report against its record type before the install, when your field is not there yet): the sheet and the lists' filter do that work.
5. **Check it before it reaches a retailer:** `python3 tools/check/check.py samples/s60_project_quotes`.

## What the retailer does

1. **Install the app.** It adds the project and its stage table, the two fields on the documents, the sheet and the Connection. No setting, no role, no outside address.
2. **Give Sales User** to the trade desk; a Sales Manager keeps projects too. Whoever sends goods out holds Stock User and accounts Accounts User, which read projects; a Retail Manager reads them too. An Accounts User names a booked till sale's or order's project.
3. **For the deliveries still to come, line by line:** the Sales Order list's **Report** view, filtered by **Project** and **% Delivered** under 100, with the item columns *Stage*, *Delivery Date*, *Quantity* and *Delivered Qty*, saved as the store's own report.

## Limits

- **The till does not name the project itself:** a till sale or order is named in Desk after it is booked, by an Accounts User, and a till order's Sales Order by the trade desk; a till quote is not named (its sale or order is). Naming it at the till is a version of your own.
- **Each section of the sheet shows what the person printing may read:** Sales User the quotes, orders and deliveries; Stock User the orders and deliveries; Accounts User the orders, deliveries, invoices and till sales; Retail Manager all of them.
- **The project is not checked against the document's customer:** the trade desk chooses it; the builder's projects show under the customer.
- **The project holds no money:** a budget, retentions and progress claims are versions of your own.
- **A till order's Sales Order and the till's own deliveries** do not carry the project by themselves: name them in Desk (unmeasured on the bench, which named a till sale).
- **The sheet lists every document naming the project**, drafts, cancelled ones and returns included; each section stops at 200.
- **A document made from several others takes the last one's project** (*Get Items From* over two orders): keep one job per document.
- **The sheet prints its documents' dates as year-month-day:** the rows `ivn_rows` returns are plain values.
- **Desk shows the records with the app's prefix** (*PP PQT Project*).
- **The builder's details are the retailer's.** Uninstalling removes the projects (the install's export keeps a copy of them) and the Project and Stage fields from every document; which project each document named goes with the fields, and the export does not keep it.
