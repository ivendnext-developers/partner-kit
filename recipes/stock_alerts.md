# Alerts before expiry and below the minimum, and a draft transfer request — the recipe

A retailer wants to know when a store's stock falls below its minimum or a batch is about to expire, and wants the stock transfer request made for it, as a **draft** a person checks and submits. iVendNext's automatic reorder makes the request but **submits** it, and it has no expiry alert; a manifest's notification runs only on your own record types, never on the retailer's batch. This recipe builds it as **an outside app on a schedule** that reads the stock, writes alerts on a record type of its own (which a manifest notification announces) and makes one draft request per store and day. It is for an iVendNext developer who has made an outside app before ([chapter 5](../guide/05_outside_apps_and_event_feed.md)).

**Reference implementation:** `samples/s27_stock_alerts/` — *Stock alerts and a draft transfer request*.

**When to use it.** A person must approve each transfer, or the retailer wants expiry alerts. If a submitted request is fine and no expiry alert is needed, configure the standard reorder instead (the card *A reminder for each store when stock is below its level*): no code.

## Steps

1. **Keep the settings in the retailer's iVendNext.** One record of your own settings type, named `Default` (below). The retailer edits it in Desk; the service reads it at each run.
2. **Read records, not reports.** The store's projected stock from *Bin*; the items' reorder rows through the item (`/api/resource/Item` with the fields `reorder_levels.warehouse`, `reorder_levels.warehouse_reorder_level`, `reorder_levels.warehouse_reorder_qty`, `reorder_levels.material_request_type`, and the filter `["Item Reorder", "warehouse_reorder_level", ">", 0]`); the batches from *Batch* (`expiry_date` up to today plus the days). A read joined to child rows sends no `order_by` on `name`: iVendNext refuses it as ambiguous.
3. **Read each batch's quantity per store from its records.** *Serial and Batch Bundle*, submitted and not cancelled, filtered on `["Serial and Batch Entry", "batch_no", "in", …]`: the bundle's `warehouse` and its rows' `batch_no` and `qty` (below 0 on an outward row), summed per batch and store (read on a sandbox, 2026-10-16: 12 received and 5 issued read 7). Leave out `voucher_type` *POS Invoice*: a till's sale not yet merged has not moved stock. Read a long list of batches in parts. If your key may not read them, say the batch's total and name no store.
4. **Key every alert.** One per kind, store, item, batch and day, and make the key the alert record's name: look it up before writing, and iVendNext refuses a second if two runs race.
5. **One draft per store and day, stamped.** A transfer request (`material_request_type` *Material Transfer*, `docstatus` 0) titled `PP-STK ⟨store⟩ ⟨day⟩`, its lines each with `from_warehouse` and `warehouse`. A transfer request has no remarks field; its title is kept as given. A later run the same day adds its lines to that draft. **A request holds an item once** (the retailer's buying settings, *allow multiple items*, off by default; the site refused a second row): a second batch of an item joins its row (quantity added), and an item already there for another move is left off and its alert says so. A line has no batch column, so name the batch in the line's description (`PP-STK batch ⟨batch⟩`) and read it back to know a batch is asked for.
6. **Never touch a request that is not yours, or not a draft.** A request without your stamp is a person's: never read or changed. A submitted one is never changed. Before adding a line, look on your open requests for that store (drafts, and submitted ones not yet transferred, stopped or cancelled): a line already there is not added again, so tomorrow's alert joins today's request.
7. **Write the lines before the alerts.** A run that stops in between finds its lines next time and writes only the alerts.
8. **Never submit.** Send `docstatus` 0 on insert and never send it on an update.
9. **Tell people through your own record.** A manifest notification on your alert type, event *New*, to a role with your prefix and to a link-to-user field of the alert.
10. **Run it on a schedule.** Any scheduler; one cron line is in the sample's README. Run one copy per retailer.

## The settings

One record of your type `⟨PREFIX⟩ Settings`, named `Default`: enabled · the source warehouse (low stock is moved from here to the store) · an optional clearance warehouse (a near-expiry batch is moved there from the store) · the days before expiry · the stores watched (a table; empty means every store but the source and the clearance) · an optional user also told.

## The alert

One record of your type `⟨PREFIX⟩ Alert` per alert, named by its key: the kind (*Low stock* or *Near expiry*) · the store · the item · the batch · the quantity (the store's projected stock; for a batch, its quantity in the store, or its total when that is not known) · whether that quantity is the store's own · the reorder level · the expiry date · the day · the transfer request it is on · the user also told.

## What iVendNext needs from you

- **The role's rights on the retailer's own record types** (a manifest grants rights only on its own): read on Warehouse, Item, Bin, Batch and Serial and Batch Bundle; read, create and write on Material Request ([the integration user recipe](integration_user.md)). Say what they reach: the key can change **any** draft transfer request in the retailer's iVendNext.
- **The settings filled in and enabled**, and the alerts role given to named people.
- **Reorder rows on the items**, and the retailer's automatic reorder left **off**, or both ask for the same stock.

## Bounds — tell the customer

- **The standard automatic reorder submits its request**, never a draft (run on a sandbox: the card *A reminder for each store when stock is below its level*). This app is how a person gets in between.
- **A notification works only on your own record.** A manifest cannot put one on the retailer's batch ([chapter 7](../guide/07_manifests.md)); the alert record is what is announced. The retailer's administrator can still set a notification on a batch in Desk (the card *A notification a number of days before a date on a retailer's record*).
- **The Administrator is never told by role.** iVendNext leaves its built-in *Administrator* out of a role's recipients (read on a sandbox, 2026-10-16: no bell entry until the role went to a named user); give the role to named people.
- **A request line has no batch column.** Its description names the batches; the person picks them when the stock moves.
- **A request holds an item once.** An item low in a store and near expiry there on the same day gets one line; the other alert has none.
- **The default stores are every warehouse that is not a group** (transit included) but the source and the clearance; list the stores to be exact.
- **A draft reserves nothing.** Low stock compares projected stock, which counts a submitted request, so the item stops being low once a person submits.
- **One alert per day.** An item still low tomorrow gets a new alert, which joins the request already open for it.
- **A row's warehouse group is not used**: the store's own stock is compared with its level.
- **The day is the service's.** Its clock, not the retailer's.

## Tell the customer

You get an alert before stock runs low or a batch expires, and a draft transfer request that a person checks, changes and submits before anything moves. Agree before you build: the source warehouse, the days before expiry, whether near-expiry stock is moved to a clearance warehouse or only announced, and who is told.

## Technical notes

- Proven on a sandbox site (2026-10-16, POS 2.0.0.648, `samples/s27_stock_alerts/README.md`): install; a planted low stock and a batch expiring in 20 days gave 2 alerts and 1 draft with 2 lines, a second run nothing new, the next day's alerts joined the same draft, the bell reached the role's holder and the user named, a hand-submitted request was left as it was, and the uninstall removed the app's records. The planted stock cannot all go: iVendNext keeps a stock movement's history, so the cancelled stock entries, their batch records and ledger rows stay, and the test batches and item stay disabled.
- Everything is the record API (`/api/resource/…`); no report and no other call.
