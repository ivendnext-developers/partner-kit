# Recipe: read many records at once — invoice lines, totals and groups in one call

**What it is for.** A report, a warehouse load or a reconciliation that needs hundreds or thousands of records. You never need one call per record: a single list call can bring back every line of every invoice in a date range, or the totals already grouped. Fewer calls means a faster run and less load on the retailer's iVendNext.

**The short version.**
- Ask for the lines in the list call itself: `items.qty` in `fields` returns one row per invoice line.
- Ask iVendNext to add up: `sum(...)`, `count(distinct ...)` and `group_by` work in the same call.
- Page through a large range, and never add a header figure (such as a grand total) across line rows.

Sample S9 (`samples/s9_bi_feed/`) reads its backfill and rebuild this way: three list calls per page of invoices.

---

## Technical notes

### 1. Lines in one call
A list call may name a child table's fields as `<table field>.<field>`. iVendNext joins the lines and returns one row per line, with the invoice's `name` on each. Filters on the invoice's own fields still apply:

```
GET /api/resource/Sales Invoice
  fields=["name","posting_date","items.item_code as item_code","items.qty as qty","items.net_amount as net_amount"]
  filters=[["docstatus","=",1],["posting_date","between",["2026-10-01","2026-10-31"]]]
  limit_page_length=0
```

- Give each child field an alias (`as qty`): the alias is the key in each row, and it keeps two tables' `idx` apart.
- One child table per call. Asking for lines and payments together returns every line with every payment (lines × payments). Make two calls, as S9 does.
- An invoice with no row of that table comes back once, with the child fields empty.
- Listing the child type directly (`/api/resource/Sales Invoice Item`) needs `parent=Sales Invoice`, and it cannot filter on the invoice's fields (it has no `posting_date`). List the invoice instead.

### 2. Totals and groups in one call
`fields` accepts `sum`, `count`, `avg`, `min`, `max` and `count(distinct …)`. The call accepts `group_by` and an `order_by` on an alias:

```
GET /api/resource/Sales Invoice
  fields=["items.item_group as item_group",
          "count(distinct `tabSales Invoice`.name) as invoices",
          "sum(`tabSales Invoice Item`.qty) as qty",
          "sum(`tabSales Invoice Item`.net_amount) as net"]
  filters=[["docstatus","=",1],["posting_date","between",["2026-10-01","2026-10-31"]]]
  group_by="`tabSales Invoice Item`.item_group"
  order_by="net desc"
  limit_page_length=0
```

- **An aggregate alone does not join the lines.** Name at least one plain line field (as above), or group by one; otherwise the call is refused or reads the invoice only.
- **Refused in `fields`:** `ifnull`, `coalesce`, `if`, `nullif`, `concat`, sub-queries and `union`. Map an empty group (for example *Uncategorized*) on your side.
- **Never sum a header figure over line rows.** An invoice with three lines repeats its `grand_total` three times. Take header figures from a call without lines, or once per invoice name.

### 3. A field of a linked record
A Link field of the record type you list can be followed one step, for example `customer.customer_group as customer_group` when listing Sales Invoice. The read needs read permission on the linked type.

You cannot follow a link from a line while listing the invoice (`items.item_code.brand` does not resolve), and the dot form does not work in `filters`. To group invoice lines by a field of the item, either:
- **read the item map once** (`/api/resource/Item`, `fields=["name","brand"]`) and group on your side — works for any date, or
- **store the value on the line**: your manifest adds a prefixed field to *Sales Invoice Item* with `fetch_from: item_code.<field>`. It fills on invoices saved after your manifest is installed; older invoices keep it empty, so use the item map for history.

### 4. Pages and volume
- `limit_page_length` defaults to **20**. `0` returns every row. For a large range, page with `limit_start` and `limit_page_length`, or split the date range.
- To read many invoices by name, list them with `filters=[["name","in",[…]]]` a page at a time (S9 uses 200).
- The product sets no per-key request limit; a site may carry a site-wide budget of request time. Reporting loads have not been measured: plan for a few list calls per run, never one call per record.

### 5. Permissions
The key reads what its user may read: the listed record type, its child rows through it, and any linked type you follow. Field-level permissions apply to child fields as well.

### Proven and not
Read from the framework's own code. S9's paged read (three calls per page, lines and payments as separate calls) is tested against a stand-in iVendNext (`samples/s9_bi_feed/tests`: no per-invoice read, every line extracted in order). Not yet run against a bench or a sandbox, and no timings are measured.
