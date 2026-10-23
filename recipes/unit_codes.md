# Unit codes at the scan (a scan source) — the recipe

![A unit scanned onto a sale with its batch and code, and a sold unit refused](../samples/s19_unit_codes/screenshots/s19_flow.gif)

A scan source lets the till's scan read the retailer's **own** unit codes: a code per pack, a tag per handset, kept in a table iVendNext already has. The cashier scans the unit and the till finds its item, its batch, its serial and whether it can still be sold. **No code is installed and nothing leaves the retailer's iVendNext**: a scan source is data. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, setting one up.

**Reference implementation:** `samples/s19_unit_codes/` — a manifest with its own unit table (a unique code, the item, the batch, *Available* or *Sold*) and a scan source over it.

**When to use it.** When units carry codes the item barcode does not (a code per pack of a batch, a tag per device) and iVendNext keeps them in a table. It fires **only on a miss**: an item barcode, a serial or a batch is still found exactly as before.

**The four rules, here.** Nothing is called and nothing leaves the retailer's iVendNext. The source names an item, a batch, a serial and a status: **the price stays the retailer's**. Your service (if you have one) writes a unit's status; the till only reads it.

## Steps

1. **Declare the table and the source in your manifest** (`recipes/manifest.md`):

   ```json
   "doctypes": [{"name": "PP UNC Unit", "autoname": "field:unit_code", "fields": [
     {"fieldname": "unit_code", "fieldtype": "Data", "label": "Unit code", "unique": 1, "reqd": 1},
     {"fieldname": "item", "fieldtype": "Link", "options": "Item", "reqd": 1, "label": "Item"},
     {"fieldname": "batch", "fieldtype": "Link", "options": "Batch", "label": "Batch"},
     {"fieldname": "status", "fieldtype": "Select", "options": "Available\nSold", "default": "Available", "label": "Status"}]}],
   "scan_sources": [{"source_name": "PP UNC Units", "record_type": "PP UNC Unit", "barcode_field": "unit_code",
                     "item_from": "item", "batch_from": "batch", "status_field": "status",
                     "available_values": ["Available"], "sequence": 10}]
   ```

   - The code field must be **unique** on its table, so one code names one unit.
   - `item_from` links to Item; `batch_from`, `serial_from` and `warehouse_field` are optional links (with `warehouse_field`, a till finds only its own store's units).
   - `status_field` and `available_values`: the statuses a unit can be sold in.
   - Or point a source at a table iVendNext already keeps (a child table on Batch: `item_from` and `batch_from` are then `parent`).
   - The source installs **switched off** (the record's own default is on; the installer turns it off).

2. **What iVendNext does after install.** It switches the source on (*Retail Scan Source*). Optionally it sets **Record the code as** to one of its own **active line attributes**: the unit's code then rides the sale's line, so the invoice says which unit was sold, and the same unit twice in one basket is refused. Recording needs a status field, so a returned unit can be sold again.

3. **Fill the table.** Your service writes the units (over the record API; the retailer's staff can also create them by hand. A file import of a manifest's record type is not something a manifest can switch on, chapter 7 step 3). **Writing *Sold* is yours**: from the event feed (`recipes/event_feed.md`) when a sale books, and back to *Available* after a return.
   - **Where the code is on the booked sale.** With *Record the code as* set (step 2), read the sale (the POS Invoice) over the record API and open its child table `custom_pos_invoice_transaction_item_attribute`. Each row has `transaction_item_attribute` (which attribute: the one the retailer chose), `item_ref` (the item the row belongs to) and `attribute_value` (the unit's code). A return carries its own rows in the same table of the return, so read the return's rows to put its units back to *Available*.

4. **What the cashier sees.**

   | Scanned | The till |
   |---|---|
   | an *Available* unit | its item lands, with its batch (and serial) |
   | a *Sold* unit | *"This unit is already sold."* |
   | the same recorded unit twice in one sale | *"This unit is already in the sale."* |
   | a unit sold on another till since its row was last written (with Record the code as) | *"This unit was just sold on another till."*, before any money moves |

   On the till: the unit scanned ![unit scanned](../samples/s19_unit_codes/screenshots/01_unit_scanned.png), its batch ![the unit's batch](../samples/s19_unit_codes/screenshots/02_the_units_batch.png), its code on the line ![the code on the line](../samples/s19_unit_codes/screenshots/03_the_units_code_on_the_line.png), and a sold unit refused ![sold unit refused](../samples/s19_unit_codes/screenshots/04_sold_unit_refused.png). On the phone: the batch and the code ![phone: batch and code](../samples/s19_unit_codes/screenshots/05_phone_the_units_batch_and_code.png), and a sold unit refused ![phone: sold unit refused](../samples/s19_unit_codes/screenshots/06_phone_sold_unit_refused.png).

5. **Two tills, one unit.** *Sold* is written by your service seconds after a sale books, so two tills can sell one unit inside that window; the check at the booking narrows it, it does not close it. Reconcile overnight.

6. **Test it.** The manifest passes the kit's checker (`tools/manifest/validate.py`) and the source holds the scan-source contract (`samples/s19_unit_codes/tests/`). Then scan on a sandbox.

## Technical notes

### What was proven where

- **Screenshots** (our test bench, 2026-10-10, the iVendNext POS app `87812e141`, the kit's demo site *Demo Retail*; frames: the till's counter frame, 1440 wide, light mode, and the phone frame, a 390 × 844 phone viewport): one *Available* and one *Sold* unit of the bench's unit item, the source switched on with the retailer's own line attribute chosen under *Record the code as*. A real browser drove the till; the checks below drove its calls.

Proven on our test bench on 2026-10-08 (iVendNext POS app at `577a8d41`), **9 of 9** checks, through the till's own scan (`api.mpos_cart.scan`) as the cashier:

| Case | Result |
|---|---|
| Install | the table and the source installed; the source **switched off** — and, off, a unit's code is not found |
| An *Available* unit, the source switched on | its item lands with **its own batch** (the unit sits in the item's second batch, so a default pick could not match it by chance) |
| A *Sold* unit | *"This unit is already sold."* |
| With *Record the code as* set to the retailer's active line attribute | the unit's code rides the line (`{"transaction_item_attribute": "Unit code", "attribute_value": "PPUNC39CFBED4"}`) |
| The same unit again in that basket | *"This unit is already in the sale."* |
| Uninstall | the table, its units and the source gone; the schema as found |

The unit's batch and code on a **booked** sale: the money kit's label for this sample (`recipes/money_kit.md`). Results: **GREEN** on 2026-10-08: the sale booked with the unit's own batch and its code on the line, every other sale as the baseline. ⚠ On a site with **no default company**, a batch or serial till sale fails to book (*"Serial and Batch Bundle: company"*) — a known behaviour of the product today; set the company default (Setup → Global Defaults) or the cashier's own.

Not run here: a unit sold on another till (*"This unit was just sold on another till."*), a source over a table on Batch (`parent`), a warehouse-scoped source, GS1 codes. The product's own tests cover them.
