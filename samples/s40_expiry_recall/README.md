# S40 — Expiry and recall (`pp_rcl`): recalls, disposal on the record, goods-in

For a pharmacy, a grocery or any retailer that sells lots with an expiry date. A Recall Officer enters the regulator's notice and presses **Block these batches**: each lot is switched off at every till and store at once, each store's stock of it is found, and so are the customers it reached. Recalled or expired stock is disposed of only against a **Disposal Record** carrying the regulator's visit. An **Expiry Worklist** lists the lots near expiry per store, and a goods receipt is refused when a lot has too few days left, unless its line carries a **Letter of Undertaking**.

**Industries:** Grocery, Pharmacy

## Start from it

```bash
ivn new acme_recall --from s40
```

## What to change

What a partner usually changes:

- **The clocks and depth:** each recall class's start and completion time and how far it traces customers, in the settings record (the defaults are Kenya's PPB table).
- **The witness:** who needs the regulator's visit (`witness_rule`, `witness_schedules`, `schedule_field` on `PP RCL Settings` in `manifest.json`).
- **Goods-in:** the minimum shelf life (`min_shelf_days`), the near-expiry window (`near_expiry_days`) and the rules in `recall.py`.
- **The records:** the five record types, the Desk buttons, the save rules and the prints in `manifest.json`; `RCL_PREFIX` names them for the service.
- **Your service's address:** `allowed_urls` in `manifest.json` names the sample's test address; write your own.

More: the [recipe](../../recipes/expiry_recall.md).

**The customer sets:** the settings record **Default** (the quarantine stores, the ERP connector's own users, the minimum shelf life and the clocks) and the role *PP RCL Recall Officer* for whoever runs recalls. The customers supplied are health data, so give the role with care.

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

### 1.0.0

- First version in the kit: a recall that blocks lots at every till and traces stores and customers; disposal only with the regulator's visit on record.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
