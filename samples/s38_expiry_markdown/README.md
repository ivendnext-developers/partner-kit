# S38 — Expiry markdown (`pp_exm`): mark down stock as its expiry date nears

A grocery, bakery or pharmacy marks down stock whose expiry date is near, so it sells before it is thrown away. The retailer sets its markdown steps once on its item groups: 25% off from 5 days before expiry, 50% off from 2 days, say. Each morning a manager ticks the lots in the Batch list and presses **Mark down**. Every ticked lot inside a step gets its own price on the retailer's selling price list, valid until its expiry date, and on every other selling price list in that currency that prices the item (a member, regional, trade or payer list), the same step's percent off that list's own price. The till already rings a lot at its own price, so the cashier does nothing new.

![What the install will change, read before you agree](screenshots/01_install.png)

**Industries:** Beauty and cosmetics, Grocery, Liquor and wine, Pharmacy

**When to use it:** the retailer's rule decides a value on many records at once, a person decides when to apply it, and iVendNext already reads the value where it matters (here: a lot's own Item Price, which the till honours).

## Start from it

```bash
ivn new acme_expiry_markdown --from s38
```

## What to change

What a partner usually changes:

- **The rule:** `markdown.py`: the percent by days left, the rounding (down to the currency's smallest unit), each lot's writes. A third step, a price point such as x.99, or a markdown by stock age.
- **The steps:** the four fields on Item Group (`pp_exm_days_1`, `pp_exm_pct_1`, `pp_exm_days_2`, `pp_exm_pct_2`) in `custom_fields` in `manifest.json`.
- **The settings record:** `price_list` and `hours_from_utc` on `PP EXM Settings`.
- **The button:** `desk_actions` in `manifest.json` (*Mark down*, on the Batch list and form).
- **The service's address:** every `host.docker.internal` in `manifest.json` is a test address; put your own there.

More: the [recipe](../../recipes/expiry_markdown.md).

**The customer sets:** the selling price list its tills sell from and its hours from UTC in *Expiry markdown settings* (`PP EXM Settings`), and the steps on each perishable item group.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- First set the price list (*Price list to mark down*) and *Hours from UTC at your store* (-5 for New York) in the *Expiry markdown settings* record `Default`, and the steps on your item group (in Desk, on Item Group: *First markdown: days before expiry* 5 and *First markdown (% off)* 25, say).
- In Desk, tick a lot close to its expiry date on the Batch list and press Mark down.
- Scan that lot at the till; it rings at its marked-down price.
- Close the till day when you are done.

## Versions

### 1.1.6

- The manifest marks its event feed `"reads_events": false`: this app reads its records itself and follows the feed only to get its own user, so the package's connection test (the one `ivn try` and the hosting dashboard read) answers the feed *Passed*, on POS build 2.1.0.728 or later. No logic changed.

### 1.1.5

- Each site call of a press may take what is left of 7 seconds from the press's start, where each was cut at 3 s: a slow read no longer makes Desk say *Mark down did not answer in time* with most of the shop's 10 seconds unused. `BUDGET_S` still decides when no new lot is started. The manifest is unchanged.

### 1.1.4

- *Try it at the till*'s first step sets the store's hours from UTC with the price list: blank, the markdown counts the day in UTC, so in an American evening its price started tomorrow and the lot rang at its full price. The service and the manifest are unchanged.

### 1.1.3

- A member pays a marked-down price too: every other selling price list in the same currency that prices the item (a member, regional, trade or payer list) gets the lot's own price, the same step's percent off that list's own price, and loses it with the markdown. A price set for one customer alone is read first and is not marked down. After you change a list's price, press Mark down again on lots already marked down; after the first press on this version, press it once more on lots already marked down and restart each store's tills, so their offline price check knows the new lot prices. Manifest 0.2.3.

### 1.1.2

- *Try it at the till* starts with the two set-up steps: the price list in Expiry markdown settings and the steps on your item group.
- Desk shows plain names (Expiry markdown settings) through the manifest's `translations` block, so a search for *markdown* finds the record. The stored names are unchanged: an installed site keeps its records. Manifest 0.2.2.

### 1.1.1

- The settings field reads *Hours from UTC at your store*, and its help says *Your store's own day*. Manifest 0.2.1.

### 1.1.0

- The role's rights beyond the feed's reads move into the manifest (`role_rights`): the install gives the feed's user its reads and the manifest the rest, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 1.0.0

- First version in the kit: a Desk button on the Batch list that writes each lot's own price by the retailer's steps, until its expiry date.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
