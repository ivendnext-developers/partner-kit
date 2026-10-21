# S30 — Units as serial numbers: each pack's printed code, tracked by iVendNext itself

Some shops track every pack or handset by its own printed code: supplements, phones, pharmacy packs. They need that code checked when stock is received, moved, counted and sold, in the back office as well as at the till. iVendNext already tracks a unit like this when the code is a **serial number** of an item that has both batches and serial numbers. This sample sets that up, moves an existing unit table onto it, and tells a lost unit from a sold one.

It is for an iVendNext Partner or a shop's administrator. **No code runs in the shop.** The scripts run once on the administrator's computer and use the shop's record API with the administrator's key.

**When to use it.** Each unit carries a code the shop must check on every stock document, not only at the till. When the codes live in a table of the shop's own and only the till needs to read them, a scan source is lighter: [S19](../s19_unit_codes/README.md).

**The doors it combines** (the kit's rule: compose doors before asking for an extension point): configuration (the item, Stock Settings, a Defective store), the record API (a migration script), and a read-only outside script (the units report). **The limit of the combination, before POS build 2.0.0.654:** the till sold a unit reliably only from the lot iVendNext picks first, and units from other lots only with a setting that changes every Desk delivery (see *Before you build on it*). From that build the till books each unit with the batch its own serial number carries, and that limit is gone.

## What the shop does

The shop's administrator, or the partner working for it, does this once, in this order:

1. **Make the set-up the shop's own.** In `config.json`, set the company, the Defective store and its parent, the items (code, name, group, price), and for a migration, the old unit table and which old item becomes which new one. The sample's names start with `PP USN` / `PP-USN`, so they are easy to tell apart from the shop's own.
2. **Make sure the shop has a default Company** (Setup → Global Defaults). Without one, a batch or serial sale at the till fails to book (*"Serial and Batch Bundle: company"*).
3. **Run `apply_config.py`.** It sets:
   - Stock Settings: *Allow existing Serial No* on (on by default), the serial and batch picker shown, *Pick Serial / Batch Based On* = Expiry;
   - a **Defective store** (a warehouse);
   - each item with **Has Batch No** and **Has Serial No**, **no Serial No Series** (a receipt must be given the printed codes, and none is made up), no automatic batch, its selling price and its barcodes.

   Run it twice and nothing doubles.
4. **Receive with the codes.** On a Material Receipt or a Purchase Receipt in Desk, the row opens *Add Serial Nos / Batch Nos*:
   - **paste** the codes, one per line, then choose the batch on each row of the table;
   - or tick *Import Using CSV file* and attach a CSV with the columns `Serial No`, `Batch No`, `Quantity` (one row per unit).

   Pasting makes the serial numbers at once, before the receipt is saved: if the receipt is abandoned they stay, inactive, and the next receipt can use them.
5. **Moving an existing unit table?** Run `migrate.py` (a dry run: it books nothing, though it saves and deletes a draft count to read the old stock), read what it would move and hold, then `migrate.py --apply`. See *The migration* below.
6. **Every day, nothing to learn.**
   - A sold unit, or one in another store, is refused at the till.
   - A return puts the sold unit back.
   - A transfer moves it.
   - An issue marks it *Consumed* (read from the code; not walked).
   - A unit in the Defective store cannot be sold.
7. **After a stock count**, run `units_report.py` to see which units the count did not find. They read *Delivered*, the same status as a sold unit, and the report tells them apart.
8. **To undo it,** run `apply_config.py --remove`. It puts Stock Settings back and undoes **only what it made or moved** on that shop: a record that was already there is never touched. It removes the price, and **retires** (*disables*) the item and the Defective store it made, because stock points at them. It cannot undo stock: received units, their batches and the receipts stay. An item's Has Serial No cannot be switched off once it has stock.

**Where it shows.** In Desk: the item, Serial No (status, store, batch), the Defective store, and the standard *Serial No Ledger*, *Serial No Status* and *Serial and Batch Summary* reports. At the till: a sold or other-store unit refused, in the till's words below.

**What leaves the shop.** Nothing but the administrator's own reads. The scripts call the shop's record API with the administrator's key. `apply_config.py` writes `.s30_⟨shop's host⟩_before.json` beside itself (the earlier Stock Settings and every record it made), so `--remove` undoes exactly that, on that shop. `units_report.py` writes a CSV only when asked (`--csv`).

## What the till says (walked on a sandbox, 2026-10-16)

| The cashier | The till |
|---|---|
| scans a unit's code | the item lands on the sale |
| scans a unit already sold, then gives its code when the till asks for it | *"✕ ⟨code⟩ was already sold (⟨sale⟩, ⟨date⟩). Refused: this exact unit has already been sold, and a unit can only be sold once."* |
| gives the code of a unit in the Defective store | *"✕ ⟨code⟩ is at ⟨Defective store⟩. Not this store's unit."* |
| returns a sold unit by its receipt | the line shows *"Serial: ⟨code⟩. Lot: ⟨batch⟩."*; the refund books a credit note, and the unit is back in the store |
| sells a unit from a lot iVendNext does not pick first | refused at payment: *"Row #1: Serial No ⟨code⟩ does not belong to Batch ⟨lot⟩"* (see *Before you build on it*) |

## The migration (`migrate.py`)

iVendNext refuses to switch on Has Serial No for an item that already has stock or sales booked. So the units move to a **new** item that has both, and the old item's lots are counted to 0. For each lot (old item, store, batch):

1. **The old stock is read** through the shop's own count: a draft Stock Reconciliation is saved, its figures are read, and it is deleted. Nothing is booked.
2. **The lot moves only if its quantity equals the coded units** the table lists for it. Otherwise it is **held** and named (*"25 in stock, 1 with a code: give the other packs a code, or count them by hand first"*). Packs without a code would otherwise leave the stock unseen. A lot whose old batch has **expired** is held too: iVendNext does not receive into an expired batch.
3. **The new item's batch is made.** Batch names are unique across items in this version, so the old batch name gets a suffix (`batch_name`, `{batch}-U` by default), and the expiry and manufacturing dates are copied. The codes are received into it as serial numbers at the old valuation rate, one receipt per store.
4. **The old item's lot is counted to 0**, one count for every lot that moved.

Run it twice and nothing doubles:
- a code that is already a serial number of its new item, in a store, is counted as moved (a code whose receipt was cancelled is received again);
- a lot already at 0 is left alone.

A code that is already **another** item's serial number is a conflict. One code is never on two items, and its lot is held. So are two codes that differ only in capitals: the till reads a typed serial in capitals. Each document it makes carries `PP USN migration` in its remarks.

The count to 0 and the receipt both post to the company's stock adjustment account at the same rate (the receipt's rows name that account, so an item's own default expense account is not used), so the value moves from the old item to the new one.

**After the migration**, switch off the old table's scan source (S19's *Retail Scan Source*): the codes are serial numbers now, and the old rows would only go stale.

The source table's fields come from `migration.fields`. The default is S19's `PP UNC Unit`, which has no store field, so `default_warehouse` names the store. A table with a store field names it in `fields.warehouse`.

## The units report (`units_report.py`)

A count with *Reconcile All Serial Nos / Batches* takes every unit of the store out, then puts the counted ones back in. A unit the count did not find therefore reads *Delivered*, just like a sold unit. The report looks at the voucher type of each unit's **latest** outward movement:

| Result | What it means |
|---|---|
| in stock | in a store (a unit the count found is here: it went out and came back in) |
| defective | in a Defective store |
| sold, till day not closed | a till sale whose day has not been posted yet |
| sold | its latest outward movement is a sale (POS Invoice, Sales Invoice, Delivery Note) |
| counted out | its latest outward movement is a count: the count did not find it |
| issued | *Consumed* (a Material Issue) |
| out | another outward movement |
| not received | made but never received |

It is not a Report Builder report: the answer needs the order of each unit's movements, which a saved report cannot express. It writes nothing to the shop.

## The files

| File | What |
|---|---|
| `config.json` | the set-up as data: Stock Settings, the Defective store, the items, the migration's source |
| `apply_config.py` | applies it (idempotent) · `--remove` undoes it |
| `migrate.py` | moves a unit table onto the new items · a dry run unless `--apply` |
| `units_report.py` | what became of each unit · `--csv`, `--only "counted out"` |
| `units.py` | the core: the migration plan and the classification, pure, no shop |
| `shop.py` | the record API calls the scripts share |
| `tests/` | the core, the migration and the set-up script against an in-memory shop · `canaries.py` |

## Run it

```bash
PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 samples/s30_units_as_serials/apply_config.py
PP_BASE=… PP_KEY=… PP_SECRET=… python3 samples/s30_units_as_serials/migrate.py            # what it would do
PP_BASE=… PP_KEY=… PP_SECRET=… python3 samples/s30_units_as_serials/migrate.py --apply
PP_BASE=… PP_KEY=… PP_SECRET=… python3 samples/s30_units_as_serials/units_report.py --only "counted out"
python3 -m unittest discover -s samples/s30_units_as_serials/tests -p 'test_*.py'
python3 samples/s30_units_as_serials/tests/canaries.py
```

`python3 tools/check/check.py samples/s30_units_as_serials` answers *NOTHING FOUND*: there is no manifest, app or sandboxed build, because the sample is configuration and outside scripts only. Its tests are the two commands above.

## Before you build on it

- **Batch and serial at the till, from POS build 2.0.0.654:** the sale books one row per unit, each with the batch its own Serial No carries, whichever lot the automatic pick would choose; a unit whose Serial No has no batch is refused (*"Serial ⟨serial⟩ has no batch. A manager sets its batch on the Serial No in iVendNext Desk."*). A unit from an expired batch is refused at payment on its own line, not inside a set; a promotion on named units names their batches too ([scan source page](../../contracts/pages/scan_source.md) §10). Walked by the product (POS train T12: a line's unit and a set's unit each booked with its own lot); not re-walked by this sample.
- ⚠ **Before POS build 2.0.0.654,** a batch+serial till sale is not reliable:
  - With *Auto Create Serial and Batch Bundle For Outward* **on** (the default), iVendNext picks a lot for the row by *Pick Serial / Batch Based On* and refuses a serial from any other lot. Walked: a unit from the second lot was refused; two units from the picked lot booked, one row each.
  - Switched **off**, a unit from the other lot booked with its own lot. But the switch is global: Desk deliveries and invoices then need their lots picked by hand.
  - Neither setting fixes a line of several units from different lots.
- **A count marks the units it did not find *Delivered***, as a sale does. `units_report.py` tells them apart.
- **Defective is a store, not a status.** A unit there is *Active* in that store, and the till refuses it as another store's unit.
- **Retired codes come back.** Issued and counted-out codes can be received again, because *Allow existing Serial No* is on by default. A code sold at the till and then received again by a receipt, instead of a return, stays refused at the till (parked: a return is the way back).
- **Offline,** the cashier scans the item, then the unit's code as its serial. The code is checked when the sale is sent (not walked).
- **Till sales read *Active* until the day's sales are posted** to the back office. A site that posts each sale at once (our sandbox did) shows *Delivered* straight away. A count taken meanwhile leaves such a unit out (iVendNext reserves units sold on an open day), so it is never taken out as *counted out*.
- **A default Company** is needed (step 2).
- **The migration's stock read is a draft count.** If the shop has none of the listed lots in stock, it refuses the draft with *"None of the items have any change in quantity or value."* and the script reads every lot as 0. A user whose language is not English gets that sentence translated, and the script stops with it instead: run it as an English-speaking user.
- ⚠ **A later version of iVendNext names a serial number by a generated name**, with the code in its serial number field. These scripts read and write the name as the code, as today's iVendNext does. On that version, the lookups by name must read the code field instead.
- **Undo cannot reverse stock** or switch Has Serial No off (step 8), the same bound as [S5](../s5_config_pack/README.md).

## Technical notes

### What was proven where

- **Laptop:** 27 tests and 13 canaries (`tests/`), each canary RED on its planted fault:
  - the migration run twice;
  - one code on two items;
  - a lot with a conflicting code counted to 0;
  - packs without a code;
  - codes that differ only in capitals;
  - a unit present at the count read as counted out;
  - a till sale after a count read as counted out;
  - movements judged out of order, or a time read as text (9:30 after 14:00);
  - a code whose receipt was cancelled counted as moved;
  - the receipt posting to an item's own expense account;
  - `--remove` touching a record it did not make.
- **The sandbox** (2026-10-16; POS app 2.0.0.650, iVendNext 15.52.0, framework 15.56.1). A two-lot item, as the shop's administrator and the store manager at the till (`/pos?frame=terminal`, 1440 wide):
  - received 3 codes pasted and 3 by CSV;
  - transferred units to the second store, where a unit sent with the wrong batch was refused (*"Serial No … does not belong to Batch …"*);
  - at the till, with outward bundles on: a unit from the second lot refused; two units of the first lot booked;
  - with outward bundles off: the second-lot unit booked;
  - the same unit again refused; returned by its receipt;
  - counted the store with one unit missing;
  - sent a unit to the Defective store, then refused at the till;
  - `units_report.py` named each unit right: 2 in stock, 1 defective, 2 sold, 1 counted out (a unit sold, returned, then missed by the count);
  - `migrate.py` dry run on a real unit table: 4 sold units skipped and 2 lots held, one with 25 in stock and 1 coded.
- **Not walked:**
  - `migrate.py --apply` on a shop (its laptop tests cover it), and with it the receipt naming the stock adjustment account;
  - `apply_config.py --remove` as it is now (undoing only what it made, per shop): the walk ran the earlier version, and the laptop tests do not exercise the retire path a real shop takes, or a barcode move;
  - an issue (*Consumed*), a unit sold again after its return, the offline scan, a Purchase Receipt (a Material Receipt was walked).

### Why this way (R6)

- *Configuration plus outside scripts* — picked. iVendNext holds every rule (sold, other store, return, transfer, count), so nothing is coded twice. About 670 lines of scripts and 470 of tests.
- *A unit table, a scan source and a service* — S19's shape. Rejected here: Desk forms would not check the codes, and the service would repeat what iVendNext already does.
- *A saved report for counted-out units* — rejected: a saved report cannot order a unit's movements.
- *Do nothing* — rejected: a count's missing units stay mixed with sales.
