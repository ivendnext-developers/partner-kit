# S25 — Gift card on spend (a big sale earns the retailer's own gift card, spendable after a hold)

A customer's sale reaches the retailer's threshold. Within the next minute the app gives them the retailer's own gift card, of the value the retailer chose, from the retailer's own gift card item. The card is spendable once the hold has passed (24 hours by default), at the till, like any other gift card. Nothing changes at the till: the cashier rings the sale as before. Staff read each card under the customer or the sale in Desk, *Gift cards*.

**Industries:** Pharmacy

## Start from it

```bash
ivn new acme_gift --from s25
```

## What to change

What a partner usually changes:

- **The rules:** `service/gcs.py` (what a sale earns and when a card is released or voided) and `service/cards.py` (the card's life).
- **The settings:** the fields of `PP GCS Settings` in `manifest.json` (`threshold`, `card_value`, `card_item`, `max_cards_per_sale`, `hold_hours`, `walk_in_customers`, `excluded_customer_groups`).
- **How the customer learns the number:** nothing sends it yet; add the message in `service/worker.py`.
- **The app's id:** `IVN_LIBRARY_APP` in `app.json`.

More: the [recipe](../../recipes/gift_card_on_spend.md).

**The customer sets:** the threshold, each card's value, the gift card item (not rechargeable, not paid out as cash, not store credit), the hold in hours, and the customer groups that never earn.

**The app's role needs:** nothing from the retailer's administrator. The install makes the role *PP GCS Integration* and the app's own user, and gives the role **read on POS Invoice**, the record type the feed follows. The manifest's `role_rights` give the rest: read on Customer and Item, read and create on Gift Card, and read, create and submit on Gift Card Balance. **Needs POS build `2.1.0.691` or later:** on an earlier site the install warns `role_rights` as unknown and skips it, and gives the feed's user no read, so the events wait; the service's log says which record type was refused (`ivn logs`) ([What goes where](../../guide/07_manifests.md#what-goes-where)).

## Run it

```bash
ivn check
ivn try
```

## Versions

### 1.2.0

- The role's rights beyond the feed's read move into the manifest (`role_rights`): the install gives the feed's user its reads, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 1.1.0

- Hosted on a schedule as a function, paid per call, instead of an always-on container.
- A cut-short answer from a retailer's site is handled as an unknown outcome, like a site that cannot be reached, never a crash.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.

### 1.0.0

- First version in the kit: a sale over the retailer's threshold earns its own gift card, spendable after a hold.
- Keeps its notes in a writable /scratch folder on CitiXsys hosting.
