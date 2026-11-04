# S28 — Merge counts, and a customer's history on the till

One app, two doors. In Desk, a stock user ticks several draft stock counts and presses **Merge counts**: one new draft count appears holding every item of the ticked counts, to check and submit. A cashier presses **Customer history** with a customer on the sale, or a back-office user opens the page for a customer, and sees that customer's last sales: the date, the store, who served, and each discount.

**Industries:** every industry

## Start from it

```bash
ivn new acme_merge --from s28
```

## What to change

What a partner usually changes:

- **How the same item merges:** `Sum` or `Last` in the settings record *PP MHS Settings* (`merge.py` holds the rule).
- **How many sales the page shows:** the settings' number (10 by default, at most 50), read in `history.py`.
- **What the page shows:** `service/history.html`, drawn with the design kit.
- **The words and refusals:** `merge.py` and `history.py`.
- **The roles:** **PP MHS Counts**, **PP MHS History** and **PP MHS Integration** in `manifest.json`.

More: the [recipe for merging](../../recipes/merge_documents.md) and the [recipe for the history page](../../recipes/customer_history_page.md).

**The customer sets:** the settings record named `Default` (*Sum* or *Last*, and the number of sales); who gets **PP MHS Counts** (those who merge) and **PP MHS History** (those who open the page); and the **PP MHS Integration** role's rights: read, create and write on Stock Reconciliation, read and create on Comment, and read on POS Invoice, Sales Invoice and User.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- Choose a customer and press Customer history; the till shows their last sales and who served.
- In Desk, tick two draft stock counts and press Merge counts; one new draft count holds both.
- Not yet pressed by us: the button on the Desk list and its dialog, and the till's own Customer history key; both were driven through the same server calls only.
- Close the till day when you are done.

## Versions

### 0.2.1

- A page that reloads opens again.

### 0.2.0

- New app makes it into an app we host, for many sites (`Hosted` in `service/app.py`, `app.json`); the install makes the app's own user.

### 0.1.0

- First version in the kit: merged stock counts, and a customer's history on the till.
- A cut-short answer from a retailer's site is handled as an unknown outcome, like a site that cannot be reached, never a crash.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
