# S22 — Customer-owned loyalty (`pp_lyl`): your logic outside, the records inside iVendNext

A retailer that runs its own loyalty programme, with its own tiers, cash back and rules, keeps the rules in your service while the members, tiers and cash back live in iVendNext. Staff see them on iVendNext's own screens, and the till shows a member's status on a **Member** key. A member can also spend the cash back at the till as *Member cash*.

**What is in it:** members, cash back, a till key, a wallet.

**Industries:** Hospitality, Liquor and wine

**When to use it:** the customer owns the rules (you write them in your own service), but staff should see the members, tiers and cash back on iVendNext's own screens, and the till should show a member's status.

## Start from it

```bash
ivn new acme_loyalty --from s22
```

## What to change

What a partner usually changes:

- **The tiers and rules:** the `records` in `manifest.json`: a customer group and a plan per tier (rank, spend, discount, cash back) and the programme's default settings (the return window, the days of spend counted). The sample has Bronze, Silver from 1,000 and Gold from 2,500. The currency, the walk-in customers and Member cash's payment method differ per retailer, so they stay in `config.json`.
- **What earns:** `earn_base` and `goods_value` in `service/money.py`.
- **The member key's answer:** `service/app.py`.
- **Member cash:** `service/wallet.py` and `wallet_mode_of_payment` in `config.json`, which must be the payment method's own name.
- **The chain's own loyalty system:** `service/outside.py`, off until its address is set.
- **The records:** the record types and the Member key in `manifest.json`.

More: the [recipe](../../recipes/customer_owned_loyalty.md).

**The customer sets:** the tiers and thresholds. A check on goods receipts (`receipt_workflow`, [the recipe](../../recipes/check_by_workflow.md)) is left out of `config.json`, so a receiving clerk's submit is untouched until the customer adds it.

**The app's role needs:** nothing from the retailer's administrator. The install makes the role *PP LYL Integration* and the app's one user, `pp_lyl@integration.invalid`; it gives the role **read on every record type the feed follows** (Customer, POS Invoice, Purchase Receipt), and the manifest's `role_rights` give the rest: write on Customer, and read on Purchase Order and Supplier (the receipt check reads the supplier a receipt names). **The app needs POS build `2.1.0.691` or later.** On an earlier site the install warns `role_rights` and `records` as unknown and skips them, the feed's user has no read, and the events wait: the service's log says which record type was refused (`ivn logs`). `python3 apply_config.py prepare`, run after the install, only checks the role exists and, when `config.json` carries a receipt check, grants the rights that check needs; it makes no user ([What goes where](../../guide/07_manifests.md#what-goes-where)).

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- Choose a member, press Member; the till shows their tier and cash back.
- Member cash has not yet run on a till; its set-up is on screens, with the payments team.
- Close the till day when you are done.

## Versions

### 1.3.1

- A sale with a total and nothing paid on it (an order placed for another store: it takes no payment at the till) earns no cash back; the sale record that takes the payment earns it. No change to a sale paid in any tender, a gift card included.

### 1.3.0

- The tiers' customer groups and plans, the programme's default settings and the role's rights beyond the feed's reads move into the manifest (`records`, `role_rights`), so the install makes them; `apply_config.py` keeps only what differs per retailer, each tier's promotion, the receipt check and the switches. The install gives the feed's user its reads, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 1.2.1

- `receipt_workflow` leaves `config.json`, so a receiving clerk's submit is untouched until the customer adds it, and the app's user holds only a read on receipts until then.

### 1.2.0

- Hosted on a schedule as a function, paid per call, instead of an always-on container.
- An opt-in link to a chain's own loyalty system: its points and offer on the Member key, each sale's earning posted to it.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.

### 1.1.0

- First version in the kit: loyalty whose logic runs in your service and whose records live in iVendNext.
- Cash back is earned on what the customer bought, so a gift card earns once.
- Serves many retailers: each one's daily balance rows under the app's own name, and a daily job tried once a day.
