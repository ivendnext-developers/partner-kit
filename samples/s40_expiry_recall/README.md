# S40 — Expiry and recall (`pp_rcl`): recalls, disposal on the record, goods-in

For a pharmacy, a grocery or any retailer that sells lots with an expiry date. A Recall Officer enters the regulator's notice and presses **Block these batches**: each lot is switched off at every till and store at once, each store's stock of it is found, and so are the customers it reached. Where the customer chooses a witness rule, recalled or expired stock is disposed of only against a **Disposal Record** carrying the regulator's visit. An **Expiry Worklist** lists the lots near expiry per store, and a goods receipt is refused when a lot has too few days left, unless its line carries a **Letter of Undertaking**.

**Industries:** Grocery, Pharmacy

## Start from it

```bash
ivn new acme_recall --from s40
```

## What to change

What a partner usually changes:

- **The clocks and depth:** each recall class's start and completion time and how far it traces customers, in the settings record. They ship blank, so a notice fills no deadline until the customer sets them, and a blank depth fills *Consumer*, so every class traces customers until the customer chooses. A Kenyan retailer fills the PPB table:

  | Class | Start within | Complete within | Depth |
  |---|---|---|---|
  | Class I | 24 hours | 14 days | Consumer |
  | Class II | 72 hours | 21 days | Retail |
  | Class III | 120 hours | 28 days | Wholesale |

- **The witness:** who needs the regulator's visit (`witness_rule`, `witness_schedules`, `schedule_field` on `PP RCL Settings` in `manifest.json`). It ships as *No disposal*; a chain with listed schedules chooses *Items with a listed schedule*.
- **Goods-in:** the minimum shelf life (`min_shelf_days`), the near-expiry window (`near_expiry_days`) and the rules in `recall.py`.
- **The records:** the five record types, the Desk buttons, the save rules and the prints in `manifest.json`; `RCL_PREFIX` names them for the service.
- **Your service's address:** `allowed_urls` in `manifest.json` names the sample's test address; write your own.

More: the [recipe](../../recipes/expiry_recall.md).

**The customer sets:** the settings record **Default** (the quarantine stores, each ticked *Is Rejected Warehouse* on its Warehouse, the ERP connector's own users, the minimum shelf life and the clocks) and the role *PP RCL Recall Officer* for whoever runs recalls. The customers supplied are health data, so give the role with care.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- In Desk, enter a recall notice for one lot and press Block these batches.
- Sell that item at the till; the blocked lot is no longer offered.
- Close the till day when you are done.

## Versions

### 1.0.3

- Its manifest is now 0.1.3. The *Recall feed* registered application's description is back to its 1.0.1 words, so a site on 1.0.1 updates in place: an update may not change a registered application's description. ⚠ Those words end *leave the feed switched off*, which is out of date: the install's one consent switches the feed on, so leave it on. Nothing else changes from 1.0.2, so a site updating from 1.0.1 meets 1.0.2's changes: the receipt, disposal and stock-count checks now go on and are flagged when the service does not answer (1.0.1 refused), under the update's one consent; set a check to refuse on its record if you want that.

### 1.0.2

- Its manifest is now 0.1.2. A recalled lot moved to a store that is not a quarantine store is left to the till's own refusal, which says where it may go (*It can leave only by a Material Issue, a move into a quarantine store … or a return to the supplier*): the app adds no second sentence about the regulator's visit. An issue of a recalled lot, and an expired lot leaving quarantine, are still disposals.

### 1.0.1

- With no settings record every check allows and a recall still blocks its lots; the witness rule ships as *No disposal*; the two receipt ticks ship off and Kenya's clocks ship blank; when the service is down the checks go on and are flagged, unless the customer chooses to refuse.

### 1.0.0

- First version in the kit: a recall that blocks lots at every till and traces stores and customers; disposal only with the regulator's visit on record.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
