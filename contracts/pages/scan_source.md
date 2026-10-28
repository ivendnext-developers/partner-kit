<!-- Source: ivendnext/iVendNext_PWA docs/extending/scan_source.md @ 60147699cce4, copied unchanged except the links: its one home is there; a defect here is a defect there: report it through the feedback forms (feedback/README.md in this repository), and we take it to the product's board. -->
# Scan source

**Contract:** [`scan_source.v1.schema.json`](../extension_contracts/scan_source.v1.schema.json)
· samples: [`samples/scan_source/`](../extension_contracts/samples/scan_source/)
· GS1 codes graded on both sides: [`tests/gs1_codes.json`](../gs1_codes.json)
· code: `business_logic/scan_source.py` (`resolve`, `validate_source`, `unit_problem`),
`business_logic/gs1.py` (the decoder; its till twin `public/js/mpos_gs1.js`), `business_logic/mpos_cart.py`
(`scan_item`).

## 1. What it is and when it fires

A shop that already keeps its units' own codes in a table — a unit barcode per pack, a tag per handset —
declares that table once, and the till's scan finds the unit: its item, its batch, its serial, and whether
it can be sold. No code is installed and nothing leaves the shop: a **Retail Scan Source** is data.

It fires **only on a miss**: an item barcode, a serial or a batch is found exactly as before and no source
is read. Sources are tried lowest *Sequence* first. A source that cannot be read is logged and skipped, so a
misconfigured table can cost a *Not found*, never a sale.

The scan also reads a **GS1 code** — a pharmacy pack's 2D code, a GS1-128 carton label — before the lookup:
its product number (AI `01`, a GTIN) finds the item, `17` refuses an expired pack (not on the receipt-less
return: an expired pack is exactly what comes back), and `10` and `21` land the batch and serial when they
belong to the item.

## 2. Version

Version 1.

## 3. What you declare

A System Manager adds one **Retail Scan Source** per table, in iVendNext Desk:

| Field | What it holds |
|---|---|
| Source name | the record's name |
| Record type | the table the codes are kept in (a child table on Batch, or any table) |
| Code field | the field holding a unit's code; it must be set **unique** on the table (or `name`), so one code names one unit |
| Item field | the field linking to Item, or `parent` for the Batch a child row sits on (`parent` works only on a child table of Batch: on another parent the source finds nothing) |
| Batch field · Serial field | optional: the field linking to Batch (or `parent`) and to Serial No |
| Status field · Sellable statuses | optional: the field holding a unit's status, and the statuses it can be sold in, one per line |
| Warehouse field | optional: the field linking to Warehouse; a till then finds only its own store's units |
| Record the code as | optional: an active Transaction Item Attribute; the unit's code then rides the sale's line (needs a status field) |
| Enabled · Sequence | switched on, and its order among sources |

**What the till does with a code a source knows:**

- a unit in a sellable status (or a source with no status field) lands as its item, with its batch and
  serial when the source names them;
- **with Record the code as**, the code rides the line, so the invoice says which unit was sold; the line
  holds that one unit of its own batch, and the same unit twice in one basket is refused;
- the receipt-less item return reads a sold unit anyway: the unit coming back is sold.

**GS1:** a symbology prefix (`]d2`, `]C1`, `]Q3`, `]e0`), a leading group separator, the bracketed form
`(01)…(10)…`, or `01` + 14 digits at the start (16 characters or more), with a correct GTIN check digit.
The GTIN finds an Item Barcode of 14, 13 or 12 digits. A bare `01` + 14 digits that already names an Item
Barcode, a serial, a batch or an item code is read as that code, not decoded. Only `01`, `10`, `17` and `21` are read; a fixed-length
AI the reader knows is stepped over; any other AI ends the read, keeping what came before it.

## 4. Every refusal, in the product's words

**What the cashier reads:**

| What happened | The cashier reads |
|---|---|
| A unit in any other status | *"This unit is already sold."* |
| The same unit twice in one basket | *"This unit is already in the sale."* |
| Before any money moves, a submitted sale carries the unit's code since its row was last written | *"This unit was just sold on another till."* |
| The batch a code names belongs to another item | *"This batch belongs to another item."* |
| A recorded unit's line holds another batch or quantity | *"Unit ⟨code⟩ is in batch ⟨batch⟩. Its line must hold that one unit of that batch."* |
| A GS1 pack past its expiry | *"This pack expired on ⟨date⟩."* |
| A GS1 serial of another item | *"This serial number belongs to another item."* |

**When the source is saved:** *"Choose the table the unit codes are kept in."* · *"⟨record type⟩ cannot hold
unit codes."* · *"⟨record type⟩ has no field ⟨field⟩."* · *"⟨field⟩ is a password field and is never read at
the till."* · *"⟨field⟩ is a field only some roles can see and is never read at the till."* (a scan answers
any cashier; a source saved before its field was put at a level keeps answering until it is saved again) ·
*"Set ⟨field⟩ unique on ⟨record type⟩ first, so one code names one unit."* · *"parent means the
Batch a row belongs to, so the table must sit on Batch."* · *"⟨field⟩ must link to ⟨Item / Batch / Serial No /
Warehouse⟩."* · *"Name at least one status a unit can be sold in."* · *"Recording the code needs a status
field, so a returned unit can be sold again."* · *"⟨attribute⟩ is not an active line attribute."*

## 5. Consent, and when it is down

Nothing leaves the shop, so there is no consent to record and no service to be down. A table the till cannot
read is logged and skipped.

## 6. Offline

A unit code reads *Not found* offline: the cashier scans the item barcode and picks the batch. A **GS1 code**
is decoded offline too, by the till's twin of the server's decoder, graded on the same table of codes: the
GTIN finds the item and `17` refuses an expired pack; the batch and serial are left for the cashier's pick.

## 7. Money and limits

No money touch: a source names an item, a batch, a serial and a status, and the price is the engine's.

⚠ *Sold* is written by your own service (from the event feed) seconds after a sale books, so two tills can
sell one unit inside that window. The check before money (section 4) narrows it; it does not close it — two
sales tendered in the same moment both pass, and a sale parked for a till is a draft until it is settled.
Reconcile overnight, and write a returned unit's row back to a sellable status so it sells again.

## 8. Worked examples

**Unit barcodes on Batch.** A child table *Batch Unit* on Batch with a unique `unit_code`, a `status`
(*Available*, *Sold*) and a Warehouse link. The source: Record type *Batch Unit*, Code field `unit_code`,
Item field and Batch field `parent`, Status field `status`, Sellable statuses *Available*, Warehouse field
`warehouse`, Record the code as *Unit code*. Scanning `HK001` lands the item of its batch, one unit, with
*Unit code: HK001* on the line; scanning it again in the same sale reads *"This unit is already in the
sale."*

**A pharmacy pack's GS1 code.** `]d2010950110153000310LOT7` + group separator + `17991231` finds the item
whose Item Barcode is `09501101530003` and puts batch `LOT7` on the line when that batch is the item's; with
`17250131`, it reads *"This pack expired on ⟨31 January 2025, in the site's date format⟩."*

## 9. Telling an AI assistant

> Declare an iVendNext POS scan source, version 1: one Retail Scan Source record per table of unit codes,
> shaped by `scan_source.v1.schema.json` (`$defs/declaration`); the samples under `samples/scan_source/`
> are known-good and known-bad records. The code field must be unique on its table, the item field must
> link to Item (or be `parent` on a child table of Batch), and Record the code as needs a status field.
> Write a unit's status back to sellable after a return, from your own service.

## 10. Units as serial numbers — the route with no table

If every unit already carries its own code, a shop can skip the scan source: each code becomes a **Serial
No** of an item that has both *Has Batch No* and *Has Serial No*. iVendNext then keeps each unit's status,
store and batch itself, every iVendNext Desk stock and sales form scans the code, and the till sells it.
Nothing is declared and no code is installed.

**Setting it up**
- The item: *Has Batch No* and *Has Serial No* on, and no *Serial No Series* (the codes are the shop's own).
- Receiving: paste the codes, or load them from a file, in the serial picker of the receipt, against their
  batch. Each Serial No then carries its batch.
- Set the site's default company and each cashier's default company: the stock record a till sale builds
  takes its company from the user.

**At the till**
- Scanning a code finds the item and the unit; each unit is its own line.
- The sale books one row per unit, each with the batch its own Serial No carries, whichever batch the
  store's automatic pick would have chosen. A markdown or an open price stays as the cashier set it.
- A unit whose Serial No has no batch is refused: *"Serial ⟨serial⟩ has no batch. A manager sets its batch
  on the Serial No in iVendNext Desk."*
- The usual unit checks apply at the scan: already sold, on an open sale, at another store, past the unit's
  own expiry date. A unit whose batch has expired scans; sold on its own line, the sale is refused at
  payment for its batch.
- The same rows are booked when an offline sale syncs, when a held sale is rung up again (the cashier scans
  the units again) and when a quote is converted.

**Limits**
- A set (a product bundle) with a batch-and-serial component books its unit with its batch. Inside a set
  a unit from an expired batch is not refused (iVendNext checks a batch's expiry on the sale's own lines,
  not on a set's components, at the till and in iVendNext Desk alike): keep expired stock off the shelf.
- A promotion restricted to named units of a batch-and-serial item must name both the units' serials and
  their batches: the promotion checks each, and the till books every unit with its batch.
- Delivering an order, or handing over a layaway, that holds serial or batch stock asks the till to scan
  the unit or pick the lot, as for every serial or batch item.
- A code sold at the till and then received again on a purchase receipt, instead of coming back as a
  return, stays refused.
- A stock count that removes units marks them *Delivered*, the same status as sold, and there is no
  *Defective* status: move faulty units to a separate warehouse, and the till refuses them as another
  store's.
