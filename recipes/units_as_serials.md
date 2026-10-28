# Every pack's own code on every stock document — the recipe

Supplements, phones and pharmacy packs often carry a printed code per pack, and the retailer must check that code when stock is received, moved, counted and sold, in the back office as well as at the till. This recipe is for an iVendNext Partner, or a retailer's administrator, setting that up.

**Reference implementation:** `samples/s30_units_as_serials/`: a set-up script, a migration from a unit table of your own, and a report that tells a counted-out unit from a sold one.

**The rules, here.** No code runs in the retailer's iVendNext. iVendNext already tracks a unit by its code when the code is a **serial number** of an item that has both batches and serial numbers, so every rule (sold, in another store, returned, transferred, counted) is iVendNext's own. The scripts run once, on the administrator's computer, through the retailer's record API with the administrator's key.

**When to use another way.** If only the till needs to read the codes, and they live in a table of your own, a scan source is lighter: [the unit codes recipe](unit_codes.md) (sample S19).

## What the store sees

| Who | Where | What |
|---|---|---|
| goods-in clerk | a Purchase Receipt or a Material Receipt in Desk | pastes the pack codes, or attaches a CSV, and picks each one's batch |
| cashier | the till | scans the item, then the pack's code; a pack already sold, or in another store, is refused in the till's own words |
| stock keeper | a transfer, a count | the codes move with the stock; a count marks the packs it did not find |
| administrator | the units report | which packs a count did not find, told apart from the packs sold |

## Steps

1. **Make a default Company** (Setup > Global Defaults). Without one, a batch or serial sale at the till fails to book.
2. **Set the items up** (S30's `apply_config.py`, from its `config.json`): each item with *Has Batch No* and *Has Serial No* on, **no Serial No Series** (a receipt must be given the printed codes, so none is made up) and no automatic batch; Stock Settings with *Allow existing Serial No* on and *Pick Serial / Batch Based On* set to Expiry; a **Defective** store. Run it twice and nothing doubles.
3. **Receive with the codes.** On the receipt's row, *Add Serial Nos / Batch Nos*: paste the codes one per line and choose each one's batch, or import a CSV with the columns `Serial No`, `Batch No` and `Quantity`. Pasting makes the serial numbers before the receipt is saved: an abandoned receipt leaves them inactive for the next one.
4. **Moving a unit table you already keep?** An item that has stock cannot be switched to serial numbers, so the packs move to a **new** item. Run S30's `migrate.py` as a dry run first: it books nothing, reads each lot's stock through a draft count it deletes, and names each lot it would **hold** (its stock does not equal its coded packs, its batch has expired, or one of its codes is already another item's). Then `migrate.py --apply`: the old lot is counted to 0 and the codes are received into the new item's batch, both at the old valuation rate on the stock adjustment account, so the value moves with them.
5. **Every day, nothing to learn.** From iVendNext POS build 2.0.0.654 the till books each pack with the batch its own serial number carries. A return puts the pack back; a transfer moves it; a pack in the Defective store is refused as another store's.
6. **After each stock count,** run S30's `units_report.py`. A pack the count did not find reads *Delivered*, the same status as a sold one; the report tells them apart.
7. **To undo,** `apply_config.py --remove` puts Stock Settings back and retires only what it made. It cannot undo stock: received packs, their batches and receipts stay.

## Limits to tell the customer

- **A count marks the packs it did not find *Delivered*,** as a sale does: read the units report after a count.
- **Defective is a store, not a status.** A pack there is refused at the till as another store's.
- **A code sold at the till and received again by a receipt,** not a return, stays refused at the till: a return is the way back.
- **Till sales read *Active* until the day's sales are posted** to the back office.
- **A pack from an expired batch** is refused at payment on its own line.
- **Offline,** the cashier scans the item, then the code as its serial; it is checked when the sale is sent (not walked).
- **What was run, and what was not:** S30's README, *What was proven where*.
