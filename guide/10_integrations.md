# 10. Integrations — system sync, estate roll-out, BI feed

**For:** a builder connecting a large retailer's own ERP, order system, warehouse system or analytics to iVendNext, or setting up many stores the same way.
**Reference implementation:** [Keep a customer's own system in step](../recipes/system_sync.md) with [`../samples/s7_system_sync/`](../samples/s7_system_sync/) · [Set up fifty stores from one file](../recipes/estate_rollout.md) with [`../samples/s8_estate_rollout/`](../samples/s8_estate_rollout/) · [Feed a data warehouse](../recipes/bi_feed.md) with [`../samples/s9_bi_feed/`](../samples/s9_bi_feed/). All three are Python, standard library only; any language can do the same.

This chapter covers the three integrations a large retailer asks for first. Each is a program you run on your own server, beside iVendNext, talking to it over the record API and the event feed (chapter 5).

## When to use it

| The customer says | Use |
|---|---|
| "Our ERP must agree with iVendNext: items, prices and stock go out, sales and returns come in, nothing lost or doubled." | the **system sync** |
| "Set up fifty stores the same way, change them together, and check them afterwards." | the **estate roll-out** |
| "Our analysts need every sale, line and payment in our warehouse, and the day must agree with the retailer's own report." | the **BI feed** |

Our own WooCommerce and Acumatica connectors are ours to build; the kit does not test or document them, and chapter 16 states what we say of their limits. Any other system is an outside app, as here. No extension point places a connector of your own on our integration framework: the extension-point library lists none (chapters 9 and 16).

**What the three share.**
- None of them writes a price onto a sale or sets a stock quantity.
- Each can be re-run safely.
- A check reports differences and **never fixes them**, because a difference in money is a person's decision.
- The sync and the BI feed pull from the event feed and key their writes, so a retry finds its own work. The sync also keeps a map between your ids and the retailer's.
- Those two use the engine transport's feed grant (chapter 5), which cannot be scoped to one application. These samples have not been run against the scoped event feed extension point. Use them where the integration is the retailer's one consumer of the feed.
- The roll-out uses the record API only.

## Steps: the system sync

1. **The retailer registers the sync** as an application following *POS Invoice* and makes an integration user. Give that user these rights: the feed's log (read and write, to mark events done), POS Invoice read, Item and Item Price create and write, Stock Entry create, write and submit, Bin and Warehouse read.
2. **OUT: what your system changed goes to iVendNext.** Your system numbers every change; the sync's cursor is the last number done. It handles each change, oldest first:
   - an **item** is created, renamed or **disabled** (never deleted: a booked sale points at it);
   - a **price** goes into the named price list;
   - a **stock movement** is a Stock Entry iVendNext books (Material Receipt in, Material Issue out). **The sync never sets a quantity.**

   Each stock write carries a key in its remarks, `PP-SYNC <your system's own id> mv:<movement number>`. The sync looks the key up before every write. The cursor moves only after the change is fully written, so a crash repeats that change and finds it by its key. ⚠ **The key must contain your system's own id.** Without it, the key can match another system's entry, and the stock is never written.
3. **IN: what iVendNext booked comes to your system, once each.** Run the feed client's loop (chapter 5). For `sale.booked` and `return.booked`, read the invoice over the API and record it in your system, **keyed on the retailer's invoice number**, so a second delivery writes nothing. A return links to its sale. Follow *POS Invoice* only, so the day's merged back-office invoice never counts a sale twice.
4. **Reconcile every night.** The check only reads, on both sides. It names each difference: a sale on one side only, a total that differs (both figures), an unlinked return, an item the sync never pushed, a price that differs, and stock on hand on each side:

   ```bash
   SYNC_KEY=… SYNC_SECRET=… python3 samples/s7_system_sync/sync.py reconcile --base … --app … --erp … --state … --warehouse … --company … --since "2026-10-04 00:00:00"
   ```

5. **Run it:**

   ```bash
   SYNC_KEY=… SYNC_SECRET=… python3 samples/s7_system_sync/sync.py run --base https://shop.example --app "My Sync" --erp erp.sqlite --state sync.sqlite --warehouse "Store - X" --company "My Company" --watch 30
   ```

   One `run` pass pushes OUT, then collects IN. **Run one instance per system per retailer:** the sync takes no lock.

## Steps: the estate roll-out

1. **Write `estate.json`:** the whole estate as data, kept in your own repository. It holds:
   - **regions** (a price list, prices, one promotion, a manager each);
   - **stores** (a code, a region, a receipt format, a cashier);
   - the reference profile new till profiles are cloned from;
   - the warehouse defaults every store carries;
   - estate-wide switches and reason codes.
2. **Run its four verbs.**
   - `plan` shows every change, object by object, and writes nothing. A blocker, such as a missing receipt format or role, is named, and `apply` refuses until it is gone.
   - `apply` makes iVendNext match the file and is idempotent. It **deletes** any user permission an estate user holds that the file does not name.
   - `verify` reads back the fields the file owns and exits 1 naming every record edited by hand and every record with the estate's prefix that is not in the file. A field the file does not own can be edited without a finding.
   - `remove` takes the estate out in reverse order.

   ```bash
   PP_BASE=https://shop.example PP_KEY=… PP_SECRET=… python3 samples/s8_estate_rollout/rollout.py plan|apply|verify|remove --estate estate.json
   ```

3. **Know three facts about iVendNext.**
   - A store's **price list, cash customer, item tax template and currency live on its warehouse**, not its till profile: iVendNext refuses a profile whose warehouse has no price list.
   - A till profile is **cloned** from the reference profile.
   - The till rings at the outlet **its user is bound to**, so assigning a cashier means binding the user to the store.
4. **Enrol the till devices as a separate step:** a user the roll-out makes has no password and no enrolled device.

## Steps: the BI feed

1. **Register a read-only application.** Its key needs the feed's log (to mark events done), and read on POS Invoice and POS Closing Entry.
2. **Pick how it picks up.**
   - `run` follows the event feed. Each invoice is read over the API and replaces its rows, in one transaction with the seen-set.
   - `backfill` re-reads invoices modified since a per-record-type watermark, to heal a gap at the end of the file.
   - `rebuild` is a full refresh into a fresh file.
   - `export` writes CSV, the same bytes for the same data.
3. **Check the day against the retailer's own report:**

   ```bash
   BI_KEY=… BI_SECRET=… python3 samples/s9_bi_feed/bi_feed.py control --base … --warehouse state/bi.sqlite --since "2026-10-04 00:00:00"
   ```

   For each POS Closing Entry it adds up the booked invoices the closing lists and compares with the closing's total. A cancelled sale stays in the warehouse as cancelled and is never revenue.

## Limits to know before you build

- **Small volume only so far.** The samples have been run with tens of sales, one at a time, never near a large retailer's day.
- **The other side has always been a local file,** not a real ERP or warehouse.
- **The sync** handles one warehouse, one company and items in Nos only. A Material Issue iVendNext refuses for negative stock stops the run.
- **The BI feed** copies each row as it was when read. A later change to a booked invoice is not followed, and a row deleted from the middle of the file needs a `rebuild`.
- **No till screens, and no offline till,** were part of any run.

## What is refused, and why

- **A stock figure typed in, or a price written onto a sale.** Stock is a movement iVendNext books; prices go to the price list.
- **Deleting an item or a store a sale points at.** iVendNext keeps its history, so the item is disabled and the store retired; a later run switches it back on.
- **The roll-out as a manifest.** A manifest may not touch a retailer's own stores, users or prices.
- **A report that fixes money.** Both reconciliations list differences and change nothing.

## When your service is down, and when the till is offline

- **Your service is down:** your cursor and the feed's queue hold your place. Restart and it catches up: nothing lost, nothing doubled (the crash tests in Technical notes).
- **Your own system is down:** not covered by the kit yet (the sample's system is a local file).
- **The till is offline:** its sales and events arrive when the till drains, so the sync and the BI feed see them late. This has not been tried with an offline till.

## Technical notes

### What the kit has proven

- **Sync, on the test site:** a full cycle with stock on hand equal on both sides; a crash on the way out (eight movements, eight Stock Entries, no key twice) and one on the way in (all four sales exactly once); a sale and its return arrived once, linked, with the units back in stock; an item deleted in the ERP was disabled, not deleted; the reconciliation named a deleted sale, a total one unit off and unpushed stock, and changed nothing. With the money kit ringing iVendNext, the sync ran as a service from the kit's start until it was stopped: **69 of 69 baskets matched**, 414 events in 27 passes, reconciliation clean with 69 sales on each side.
- **Roll-out:** `plan` on an empty estate listed all 51 stores, their price lists, prices, promotions, users and permissions, and wrote nothing; the second `apply` changed nothing; changing one region's price moved exactly two records; `verify` went red on a store edited by hand and on a stray warehouse; the same basket cost 198.00 then 178.20 with the region's promotion on, and **the booked sale equalled the till's preview**; `remove` left nothing live; the money kit matched 67 of 67 with the estate applied.
- **BI feed:** every header, line and payment equalled the retailer's record; a second load added only the new invoices; a crash mid-load left each invoice once; a cancelled sale was not revenue; all five closings agreed, and a total one unit off or an invoice deleted turned the check red; a rebuild equalled the incremental file; one `backfill` healed a missing tail.

### What it has not

- **The scoped feed** (chapter 5): every run used today's unscoped grant. **A real ERP:** the other side is a local file.
- **Volume:** the largest run was 69 sales and 414 events, one at a time. Nothing is measured near a large retailer's day.
- **Roll-out:** the site had **one real store**; the 51 were warehouses and profiles made for the test. No sale was rung at a store of another region. Roles, user permissions and the `plan` blockers (a missing receipt format, item or role) are tested on a laptop only.
- **Sync:** a price change, an item rename, a second price list, the cancelled-sale handler and a return whose sale predates the sync were laptop tests only; a Material Issue iVendNext refuses for negative stock stops the run; one warehouse, one company, items in Nos only.
- **BI feed:** rows are as of extraction (a later change to a booked invoice is not followed); a row deleted from the middle of the file needs a `rebuild`; one invoice is read per event; `backfill` after a long outage and `rebuild` at volume were not run; payments are the invoice's payment rows, with change given not netted.
- **The till app's version:** the promoted-sale result was taken at the test site's pinned version; later changes to cart, tender and discount are not re-checked.
- **The till screens, and offline,** for all three.

### Notes on the steps

- **The sync's rights.** The grant in step 1 of the system sync is the one measured on the test site.
- **Why the key carries your system's id.** A key of the movement number alone found an earlier system's entry and wrote no stock at all.
- **Offline.** Offline itself was not tested.

## See also

[4. Configure first](04_configure_first.md) · [5. Outside apps and the event feed](05_outside_apps_and_event_feed.md) · [14. Testing and release](14_testing_and_release.md) · [16. Possible, not possible, limits](16_possible_not_possible.md)
