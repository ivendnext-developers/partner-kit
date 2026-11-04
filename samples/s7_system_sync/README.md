# S7 — a system sync: a customer's own ERP, order system or warehouse system in step with iVendNext

This sample keeps a customer's own back-office system in step with iVendNext. Items, prices and stock go out to iVendNext; booked sales and returns come back, once each; a nightly report names anything the two disagree on and never fixes it. It runs on the customer's own server, outside iVendNext, over the record API and the event feed.

**Industries:** every industry

**When to use it:** another system is the master for items, prices or stock, and it must also learn of every sale.

## Start from it

**Copy by hand: not an app made here.** Copy `samples/s7_system_sync/` into your own repository and change the names as this page says.

## What to change

What a partner usually changes:

- **The customer's system:** `erp.py` is a stand-in (a SQLite file). Replace it with a client of the customer's own ERP that gives the same changes and takes the same orders and returns.
- **The company and the store:** `--company` and `--warehouse`; one of each per run.
- **The feed's name:** `--app`, the name of the Registered Application that follows POS Invoice.
- **The identity map and what goes out:** the out, in and reconcile steps in `sync.py`.
- **What a movement costs:** send the cost. A movement with no cost takes the item's rate from the ledger, and a new item with no ledger rate books at 0, with nothing to say so.

More: the [recipe](../../recipes/system_sync.md).

**The customer sets:** one integration user for the sync ([integration user](../../recipes/integration_user.md)) with read and write on the event log, read on POS Invoice, Bin and Warehouse, create and write on Item and Item Price, and create, write and submit on Stock Entry; a Registered Application that follows POS Invoice; and the one warehouse and company it serves.

## Run it

```bash
SYNC_KEY=… SYNC_SECRET=… python3 samples/s7_system_sync/sync.py run --base https://shop.example --app "My Sync" --company "My Company" --warehouse "Main Store"
python3 -m unittest discover -s samples/s7_system_sync/tests -p 'test_*.py'
```

## Versions

### 1.0.1

- iVendNext values a movement with no cost from the ledger, instead of booking it at 1.

### 1.0.0

- First version in the kit: a customer's own order or warehouse system kept in step with iVendNext.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
