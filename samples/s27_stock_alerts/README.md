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

Then, from `service/stk/` in the app you made, with the key of a user that holds your app's role ending *Integration* (your prefix, then Integration): `STK_KEY=… STK_SECRET=… python3 run.py --base https://shop.example`. One run each time it starts; start it once a day from any scheduler.

## Try it at the till

- Try installs the lists but does not run the alerts. In Desk, fill your app's settings record `Default` (in the list that starts with your prefix and ends in *Settings*; press *New*, its name fills itself as `Default`): the source warehouse, the days before expiry; tick *Enabled*, and give an item a reorder row of type *Transfer* for a store whose stock is below its level.
- On the tried site, make a user of your own, give it your app's role ending *Integration* (your prefix, then Integration) and press *Generate Keys* on it. Then run it once, as [Run it](#run-it) says, with `--base https://<the tried site>`. Your app's alert list (your prefix, ending in *Alert*) shows the low stock, and a draft transfer request titled with your prefix, its words joined by hyphens, then the store and the day waits in Desk for a person to submit.

## Versions

### 0.2.3

- *Try it at the till* names the settings record, the alert list and the draft request as your app has them (they start with your prefix), never the sample's own `PP` names, which a tried or published app does not have. Words only.

### 0.2.2

- *Try it at the till* names the role as your app has it (your prefix, then Integration), never the sample's own name, and points at *Run it* for the command. Words only.

### 0.2.1

- *Run it* gives the command, and *Try it at the till* says Try does not run this part, how to run it against the tried site and what you then see. Words only; no service or rule changes.

### 0.2.0

- The role's rights move into the manifest (`role_rights`): the install makes the role and gives it its reads and its Material Request rights; the retailer makes the integration user and its key, which this app (it has no event feed) does not get from the install. Needs POS build `2.1.0.691` or later. (An earlier note here said the install makes the app's user: it makes none for an app with no feed.)

### 0.1.0

- First version in the kit: stock alerts and a draft transfer request.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
