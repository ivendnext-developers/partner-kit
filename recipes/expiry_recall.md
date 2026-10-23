# Expiry and recall: block recalled lots and dispose of them on the record — the recipe

A regulator recalls a batch; a delivery arrives with six weeks of shelf life; expired stock must be destroyed in front of an inspector. This recipe is for an iVendNext Partner, or the CitiXsys Consulting Team, building expiry and recall for a pharmacy, a grocery or any retailer that sells lots with an expiry date.

**Reference implementation:** `samples/s40_expiry_recall/` — *Expiry and recall*: two Desk buttons, three document checks (a goods receipt, a stock entry, a stock count), five record types, one small service. Its App library copy is *Expiry and recall* (`ivendnext_rcl`).

**The four rules, here.** Your service's code never runs inside the retailer's iVendNext: Desk calls it when a button is pressed, and iVendNext asks it before a document is submitted. Your service writes only the app's own records and one field of the retailer's (a lot's `disabled`), with its own key and its own rights. It never touches money.

## What the officer, the store and the clerk see

| Who | Where | What |
|---|---|---|
| Recall Officer | a **Recall Notice**: the regulator's reference, class, depth, when it was received, the lots | **Block these batches**: the lots switched off at every till at once; each store's stock found; the customers supplied listed; a **Store Progress** record per store; the clock filled from the class |
| each store's stock keeper | its **Store Progress** | the quantity found; moves it to quarantine (the retailer's own transfer), writes what it moved, marks it *Done* |
| Recall Officer | a **Disposal Record**, then the regulator's visit | the record locks once the visit is recorded; the disposal issue goes through only naming it |
| pharmacist | an **Expiry Worklist** | **Refresh**: lots near expiry per store, and medicine lots with no expiry date |
| goods-in clerk | a **Purchase Receipt** | refused when short-dated, unless the line carries a Letter of Undertaking with its days |

## Steps

1. **Declare the doors in your manifest** (sample S40's `manifest.json`): two `desk_action` services and their buttons, on your own record types (a record type that is never submitted ticks *on a draft*), and two `doccheck` services:

   ```json
   {"key": "receipt", "point": "doccheck", "endpoint_url": "https://your.server/check/receipt", "timeout_seconds": 6,
    "down_answer": "refuse",
    "settings": {"record_type": "Purchase Receipt",
                 "send_fields": "name, supplier, posting_date, is_return, supplier_delivery_note, items(item_code, qty, batch_no, serial_and_batch_bundle, acme_rcl_pack_expiry, acme_rcl_lou, acme_rcl_lou_days)",
                 "on_validate": false, "fill_fields": ["acme_rcl_short_dated"]}}
   ```

   A field you add to a retailer's table (`acme_rcl_pack_expiry` on the receipt's lines) may be sent; `fill_fields` names only fields on the record itself.
2. **Block with the row as read.** Write `{"disabled": 1, "modified": <the lot's modified as read>}`, so an edit made meanwhile is never written over. **Never save a lot with no expiry date:** with *Has Expiry Date* on and a shelf life set, iVendNext fills it from the manufacturing date plus the shelf life, a guess.
3. **Trace from the stock ledger, not the lot read.** The retailer's lot read (`/api/method/ivendnext_mpos.api.v1.get_batch_qty`) leaves out a disabled lot, so after the block it reads nothing. Read the bundles instead, with their lot rows:

   ```python
   rows("Serial and Batch Bundle", ["name", "voucher_type", "voucher_no", "warehouse",
                                    "`tabSerial and Batch Entry`.batch_no", "`tabSerial and Batch Entry`.qty"],
        [["Serial and Batch Entry", "batch_no", "in", lots], ["docstatus", "=", 1], ["is_cancelled", "=", 0]])
   ```

   Leave a POS sale's own bundle out of the stock (it books nothing until the day's sales are merged). For the customers, keep both: when a POS day closes iVendNext moves the sale's bundle onto the day's merged invoice, so a till sale is listed under its POS sale before the close and under the merged invoice after it, never twice (a walk-in sale's merged invoice names the walk-in customer).
4. **Judge a receipt by the pack, not the lot, and from today.** With a shelf life set, iVendNext can work a lot's expiry out from its manufacturing date, and a later edit of either date leaves no trace: ask for the date printed on the pack on the line (`acme_rcl_pack_expiry`) and refuse a lot that does not match it. Count days left from the later of today and the posting date, so a backdated receipt lets nothing older in. An expired lot is refused before any exemption or letter, and a line rejected whole is not judged.
5. **Flag the ERP, refuse the Desk.** The check is not told who called it through which door; the settings name the ERP connector's own users (never a person's login; compared without case), and for them the answer is `fill` (the problems in one field, at most 140 characters) instead of `refuse`. When the app cannot read its settings it cannot tell them apart, and refuses.
6. **A disposal needs the visit, once.** Treat as a disposal any material issue of a witnessed item, and any stock leaving a quarantine store, or a blocked or expired lot, for anywhere but a quarantine store, whatever the purpose. Refuse it unless it names a record for the line's store whose workflow state is *Visit recorded*, with the officer, authority, date (not after the posting date) and signed form, and whose lines still cover the lot and quantity, in the stock unit, after what earlier submitted issues naming the same record drew on it. If the item has no field for its schedules, refuse loudly. Subscribe a third check on Stock Reconciliation: a count may not lower such stock.
7. **Lock the record, and check the lock.** A workflow's *allow edit* does not stop a save; the `locked_in_state` save rule does, and it installs switched off. So the disposal check reads that rule and refuses every disposal while it is off.
8. **Test it** on your laptop (S40's tests and canaries), then on a sandbox: install, the app's user and its rights, the consent, then the scenario below.

## Limits to tell the customer

- **A Desk document naming a blocked lot by hand is not refused yet.** The online till never offers a disabled lot; a Desk delivery or invoice typed with it submits until the POS app refuses disabled lots on every stock document.
- **An offline till keeps a blocked lot until it syncs.** Press again after the tills sync: a sale they made offline is then traced.
- **A schedule set only on an item group is not read.** Give each controlled item its own schedule, or choose *Every disposal*.
- **A refused draft submitted again unchanged within 5 minutes gets the same answer** (the document check's *asked once*): after the visit is recorded, the clerk submits the issue again after 5 minutes.
- **An ERP connector that posts stock entries** (SAP does, every few minutes, as its own user) has them flagged, never refused; while your service is down its sync stops, because the stock-entry check refuses (or choose *allow and flag* and accept an unwitnessed Desk disposal during an outage).
- **A disposal by a return to the supplier is not checked**, nor a Desk *Material Receipt*.
- **A disconnected app** has every check answered by its down answer.
- **A recall reaching thousands of sales** may not finish within 10 seconds: press again.
- **A lot swapped inside the same bundle within 5 minutes** is not asked about again (the check is sent the bundle, not its lots).
- **Customers supplied are health data.** Keep the notice to the Recall Officer and System Manager.

## Technical notes

### What was proven where

- **Laptop:** S40's 98 tests and 63 canaries.
- **Our Pharmacy test bench** (2026-10-22, POS app at `84185344`), two full runs, each green: the install switched off; a recall of two lots across two stores and three customers (a till sale whose day closed, a Desk invoice, a delivery); the till then offering no blocked lot and booking a good one; the quarantine move, a disposal refused without a record and with an unrecorded visit, and submitted once the visit was recorded, the record then locked; short-dated receipts refused and passed with a Letter of Undertaking; a worked-out expiry refused until the pack's was typed; the ERP's receipt flagged; both checks with the service down.
- **Not proven:** Handheld's receiving path (not installed on the bench).
