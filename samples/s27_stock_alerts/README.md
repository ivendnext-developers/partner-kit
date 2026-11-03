# S27 — Stock alerts and a draft transfer request

The retailer is told when a store's stock falls below its reorder level, or when a batch is close to its expiry date, and finds a **draft** stock transfer request already made from those alerts: one per store and day, for a person to check, change and submit. The app never submits anything. iVendNext's own automatic reorder submits at once and has no expiry alert; this app is for the retailer that wants a person in between.

**Industries:** Grocery

## Start from it

```bash
ivn new acme_stock_alerts --from s27
```

## What to change

What a partner usually changes:

- **The rules:** `alerts.py`: low stock against the reorder row, the expiry window, the lines per store.
- **The settings the customer fills:** the fields of `PP STK Settings` in `manifest.json` (source warehouse, days before expiry, clearance warehouse, stores watched, a user to tell).
- **Who is told:** the notification *PP STK New Alert* in `manifest.json` (the bell; change `channel` to `Email` for e-mail) and the role **PP STK Alerts**.
- **A reminder with no service:** `batch_expiry_package.json` is a second package that e-mails every **Stock Manager** 30 days before a batch expires. Change the days, the role or the channel before you install it.

The app runs once each time `run.py` is started: start it once a day from any scheduler.

More: the [recipe](../../recipes/stock_alerts.md).

**The customer sets:** the source warehouse, the days before expiry and optionally a clearance warehouse in **PP STK Settings**; the reorder rows on its items (the store, the level, the quantity, the type *Transfer*), with its own automatic reorder left off; and who holds **PP STK Alerts**.

## Run it

```bash
ivn check
ivn try
```

## Versions

### 0.1.0

- First version in the kit: stock alerts and a draft transfer request.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
