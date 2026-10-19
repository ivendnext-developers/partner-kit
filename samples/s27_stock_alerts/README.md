# S27 — Stock alerts and a draft transfer request

## What the shop does

The shop is told when a store's stock falls below its reorder level, or when a batch is close to its expiry date, and finds a **draft** stock transfer request already made from those alerts: one per store and day, for a person to check, change and submit. The app never submits anything. iVendNext's own automatic reorder makes a request too, but submits it at once, and it has no expiry alert; this app is for the shop that wants a person in between.

| What happens | When |
|---|---|
| A *Low stock* alert, and a line moving the reorder quantity (or the shortfall, when larger) from the source warehouse to the store | a store's projected stock is below the level on the item's reorder row, and the row's type is *Transfer* |
| A *Low stock* alert with no line | the reorder row's type is *Purchase*, *Material Issue* or *Manufacture* |
| A *Near expiry* alert for each store that holds the batch | a batch expires within the settings' days, or has expired and is still in stock |
| A line moving the batch's item from the store to the clearance warehouse, its description naming the batch; a second batch of that item joins the same line (the quantities added, both batches named) | the settings name a clearance warehouse |
| The alert, with no line | the item is already on today's draft for another move (in from the source and out to clearance): a request holds an item once |
| The shop's bell tells the people with the role **PP STK Alerts**, and the user named in the settings | an alert is written |
| Nothing new | the same alert was already written today, or its line is already on an open request of the app for that store |
| Today's draft gains the new lines | the app runs again the same day and finds new alerts |
| A request is left exactly as it is | it was made by a person (it has no stamp), or a person has submitted it |

**Bounds, said plainly.**
- **A draft, never a submitted request.** A person submits it; until then it moves nothing and reserves nothing. Low stock compares the store's *projected* stock, as the standard reorder does, so once a person submits the request the item stops being low.
- **One alert per kind, store, item, batch and day.** An item still low tomorrow gets tomorrow's alert, and that alert joins the request already open for it rather than making a second one.
- **A request line has no batch column.** The clearance line's description names each batch (`PP-STK batch ⟨batch⟩`), and the person picks them when the stock moves. Keep those words if you edit the description: the app reads them to know a batch is already asked for.
- **A request holds an item once**, as the shop's buying settings allow by default (*allow multiple items* off: the site refused a second line of the same item). So an item low in a store and near expiry there on the same day gets the low-stock line; its near-expiry alert says it has no line.
- **A near-expiry batch already on a submitted request is not asked for again** until that request is transferred, stopped or cancelled. If the batch is still in the store after that, the next run asks again.
- **The stores watched by default are every warehouse that is not a group**, other than the source and the clearance: a transit or rejected-goods warehouse included, and the source's own stock is never alerted. List the stores in the settings to be exact.
- **A request is the app's by its title.** A person's copy that keeps the title `PP-STK ⟨store⟩ ⟨day⟩` is taken for the app's draft; change the title of a copy.
- **A till's sale not yet merged is not counted** in a batch's quantity per store: its stock has not moved yet.
- **The Administrator is never told by role.** The shop leaves its built-in *Administrator* out when it tells a role, so give **PP STK Alerts** to named people.
- **The schedule is yours.** The app runs once each time it is started; start it once a day, or each hour (the alerts and lines do not repeat).
- **Run one copy per shop.** Two copies at once could each add the same line to a draft before either sees the other's.
- **A row's warehouse group is not used.** The store's own projected stock is compared with its level.
- **The alert's day is the service's day** (its clock, not the shop's).

## What the shop does to set it up

1. Install `manifest.json` (the shop's administrator, on the install screen; on your sandbox, `tools/deploy/deploy.py`). It adds `PP STK Settings`, `PP STK Alert`, the notification *PP STK New Alert* (bell) and the roles **PP STK Integration** and **PP STK Alerts** (both empty).
2. In **Role Permissions**, give PP STK Integration **read** on Warehouse, Item, Bin, Batch and Serial and Batch Bundle, and **read, create and write** on Material Request. A manifest grants rights only on its own record types ([the integration user recipe](../../recipes/integration_user.md)). ⚠ With these rights the key can change **any** draft transfer request in the shop: give the role to this app's user alone.
3. Make the app's integration user with that role and generate its API key.
4. Fill **PP STK Settings** named `Default`: the source warehouse (the stock replenishment comes from), the days before expiry, an optional clearance warehouse, the stores watched (empty: every store but the source and the clearance), an optional user to tell; tick **Enabled**.
5. Give **PP STK Alerts** to the people who act on the alerts.
6. Put reorder rows on the items (the store, the level, the quantity, the type *Transfer*), as for the standard reorder. Leave the shop's automatic reorder **off**, or both will ask for the same stock.
7. Run the service on a schedule with the user's key (below).

**What leaves the shop.** The shop calls nothing outside. The service **reads** the warehouses, the items' reorder rows, the stock of the watched stores, the batches and their records, and the open transfer requests. It **writes** alerts and draft transfer requests, and adds lines to its own drafts.

## Run it

```bash
python3 -m unittest discover -s samples/s27_stock_alerts/tests -p 'test_*.py'
python3 samples/s27_stock_alerts/tests/canaries.py
```

On a sandbox, with the integration user's key in the environment (never on the command line, never committed):

```bash
STK_KEY=… STK_SECRET=… python3 samples/s27_stock_alerts/run.py --base https://your-sandbox.example
```

Once a day at 06:00, from any scheduler; with cron:

```bash
0 6 * * * cd /srv/partner-kit && STK_KEY=… STK_SECRET=… python3 samples/s27_stock_alerts/run.py --base https://shop.example >> stk.log 2>&1
```

Each run prints one line: the alerts written, the requests made, the lines added, the lines already on a request, the alerts with no line, and whether each batch's quantity per store could be read.

## The files

| File | What |
|---|---|
| `alerts.py` | the rules, pure: low stock against the reorder row, the expiry window, the alert's key, the request's stamp, the lines per store |
| `run.py` | the service: the shop over the record API, one run (read, alerts, the draft per store and day, then the alert records) |
| `manifest.json` | the settings, the alert, the stores table, the two roles, the bell notification |
| `tests/test_s27.py` | 32 laptop tests: low stock and its quantity, a row with no level, a store not watched, a run twice, the next day, a run that stopped half-way, the stamp, a person's draft, a submitted request, the expiry window's edges, a batch per store, two batches of one item, one item for two moves, no clearance warehouse, a batch quantity that cannot be read, the per-store sum with an outward row, what an update sends, settings switched off |
| `tests/test_manifest.py` | the manifest: valid, every field the service reads and writes declared, the rights, the notification on the app's own record |
| `tests/canaries.py` | each guard removed in turn: its test must go RED (27 of 27) |

## Technical notes

- **Records only, no report.** The stock comes from *Bin* (the projected quantity), the reorder rows from the item (read as `reorder_levels.⟨field⟩` through `/api/resource/Item`), the batches from *Batch*, and **each batch's quantity per store from the batch records of submitted stock movements** (*Serial and Batch Bundle*: the bundle's warehouse and its rows' `batch_no` and `qty`, which is below 0 on an outward row, summed; cancelled ones and a till's sale not yet merged left out; read 100 batches at a time). If the key may not read those records, the alert says the batch's total, names no store and makes no line.
- **Why a stamp in the title.** A transfer request has no remarks field; its title is kept as given (the shop writes one only when it is empty). The service's draft is titled `PP-STK ⟨store⟩ ⟨day⟩`; a request without that title is a person's, and the service never reads or changes it.
- **Why the alert's name is its key.** `⟨day⟩ LOW|EXP ⟨hash of store, item, batch⟩`: the service looks it up before writing, and the shop refuses a second record of that name if two runs race.
- **One row per item.** A clearance line for an item already on the draft for the same move is added to that row (quantity and batch); for another move it is left off. A line is already asked for when its item, both warehouses and (for clearance) its batch are on an open request of the app for that store.
- **Lines before alerts.** A run that stops after writing the lines finds them on the draft next time and writes only the alerts.
- **The notification** is on the app's own *PP STK Alert*, as a manifest notification must be ([chapter 7](../../guide/07_manifests.md)): the bell, by role and by the alert's *Also told* field (a link to a user). Change `channel` to `Email` for e-mail.

### What was proven where

- **The laptop tests** (`tests/`): everything above against a stand-in shop; `canaries.py` turns each guard off in turn and its test goes RED.
- **A sandbox site** (2026-10-16, POS 2.0.0.648, manifest 0.1.0, the service on a laptop with the site's integration user): installed with `tools/deploy`; a reorder row (level 25, quantity 10, *Transfer*) on an item with 20 in a store, and a batch of 12 expiring in 20 days received into that store. Run 1: **2 alerts and 1 draft request with 2 lines** (10 from the source warehouse to the store; 12 from the store to the clearance warehouse), the batch's quantity per store read from its records. Run 2: nothing new, the draft unchanged. A run for the next day: 2 new alerts, both joined the open draft, no second request, and the bell reached the role's holder and the user named in the settings. A person changed the quantity to 8 and submitted the draft by hand; the next run wrote nothing and the submitted request was unchanged; a run two days on wrote no low-stock alert (the projected stock now counts the request) and one near-expiry alert that joined the submitted request, with no new draft. The uninstall exported and removed the app's records; users, roles, permission rows and stock were as found. A second run the same day, after the review's changes: two batches of the item (12 received and 5 issued of one, 9 of the other) read **7 and 9** in the store, the outward row taken off; the request held **one row of 16 naming both batches**; a second run wrote nothing, and the next day both alerts joined that draft. The site refuses a second row of the same item on a request (its default), which the first build had not met. Not run on a sandbox: a *Purchase* row, a batch in two stores, no clearance warehouse, an item low and near expiry in one store, a key that cannot read the batch records, a person's own draft beside the service's, a run that stops between the lines and the alerts, a new line added to an existing draft (the person's edit, the same call, kept both rows), the submitted-request case after the review's changes (laptop only); not run at all: a till's unmerged sale, more than 100 expiring batches, the e-mail channel, two copies at once, a reorder row with a warehouse group, a scheduler.
