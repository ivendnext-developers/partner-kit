# S35 — Call-centre orders by district (`pp_cco`): a button that routes a phone order

A customer phones the call centre; the agent enters the order once, in Desk, and presses **Send to store**. The order then ships from the store that serves the customer's district and appears on that store's own list. The button's service changes that same record: the warehouse of a draft Sales Order and of every line on it.

![The app's card in the App library](screenshots/01_app_library_card.png)

**Industries:** Hospitality, Pharmacy

**When to use it:** you want a press in Desk to decide something about the record from data iVendNext already holds, and write the answer back onto it.

## Start from it

```bash
ivn new acme_district_orders --from s35
```

## What to change

What a partner usually changes:

- **The routing:** `route.py`, which walks the territory up the tree to the first **Serving store** and writes it on the order and every line.
- **The button:** `desk_actions` in `manifest.json` (its label and the roles that see it), on a draft Sales Order's form.
- **The field:** the **Serving store** field on Territory, in `custom_fields` in `manifest.json`.
- **The service's address:** every `host.docker.internal` in `manifest.json` is a test address; put your own there.
- **The answers the agent reads:** the sentences in `route.py`.

More: the [recipe](../../recipes/call_centre_orders.md).

**The customer sets:** a **Serving store** (a warehouse of the orders' company, never a group) on each district of its Territory tree; a district left empty takes the store above it.

**The app's role needs:** nothing from the retailer's administrator. The install makes the role *PP CCO Integration* and the app's own user, and gives the role **read on Sales Order**, the record type the feed follows. The manifest's `role_rights` give the rest: write on Sales Order, and read on Territory, Customer (a sales order names its customer), Address (the order's save reads its customer's billing and shipping addresses again, so the app's user reads them too) and Warehouse. Give the role to no one else: it reaches every sales order, customer and address. **Needs POS build `2.1.0.691` or later:** on an earlier site the install warns `role_rights` as unknown and skips it, so **Send to store** says the app may not read or change the order; install the build, then press it again ([What goes where](../../guide/07_manifests.md#what-goes-where)).

## Run it

```bash
ivn check
ivn try
```

## Versions

### 1.1.1

- Manifest 0.2.1. The app's role also reads Address: the order's save reads its customer's addresses again, so an order with a billing or shipping address was refused (*may not read or change this order*). **Send to store** now sends it. The service is unchanged.

### 1.1.0

- The role's rights move into the manifest (`role_rights`), and the install gives the feed's user its read on Sales Order, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 1.0.1

- The press asks no confirmation.

### 1.0.0

- First version in the kit: a Desk button that routes a phone order to its district's store.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
