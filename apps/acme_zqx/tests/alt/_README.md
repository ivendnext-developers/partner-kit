# S53 — Alterations and made-to-measure tickets (`acme_zqx`)

A fashion store's ticket for each alteration and each made-to-measure piece, kept in iVendNext Desk: what to do to which garment, the measurements, the fitting, the date it is ready, the tailor's progress, a slip for the customer with a tag for the garment, the tickets due, and who collected it. The charge and any deposit are rung at the till as before. The app calls nothing outside: no service, no outside address.

![What installing it changes, read before the install](screenshots/01_install.png)

**Industries:** Fashion and footwear

**When to use it:** a store alters what it sells (a hem, a waist, a sleeve) or makes to measure (a suit, a dress), and its tickets are on paper today.

## Start from it

```bash
ivn new acme_alterations --from s53
```

## What to change

What a partner usually changes:

- **The ticket's fields:** `ACME ZQX Ticket` and its child tables `ACME ZQX Garment` and `ACME ZQX Measure` in `doctypes` in `manifest.json`.
- **The measurements:** the list of measures a store or a country uses (`ACME ZQX Measure`).
- **The steps:** the six states of the workflow in `workflows`; who may edit each (`allow_edit`).
- **The slip and tag:** the print format `ACME ZQX Ticket` in `print_formats`.
- **The report:** *Tickets Due* in `reports`.
- **The naming series:** `ALT-` in the ticket's `autoname`.

The ticket holds no amount: the charge and the deposit belong to the till's sale and order.

More: the [recipe](../../recipes/alteration_tickets.md).

**The customer sets:** who gets the role **Sales User** (they take, move and print tickets), and its own Notification on **Ready to collect** to tell the customer by e-mail or SMS; the app sends nothing itself.

## Run it

```bash
ivn check
ivn try
```

## Versions

### 0.1.3

- Desk shows plain names (Alteration ticket, Taken, With the tailor) through the manifest's `translations` block, so a search for *alteration ticket* finds the record. The stored names are unchanged: an installed site keeps its records.

### 0.1.2

- The slip says *Collect at* with the store's own name (a read-only *Store name* field), not the warehouse's record name with the company suffix. A slip saved before the update prints the old name until it is saved again.

### 0.1.1

- The *Ready to collect* field's help text reads as a sentence, not a code condition.

### 0.1.0

- First version in the kit: alterations and made-to-measure tickets, from a manifest only.
