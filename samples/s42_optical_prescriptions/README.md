# S42 — Optical prescriptions and lab orders (`pp_opt`)

The worked sample for an optical store: eye tests, lab jobs and one rule at the till. The retailer's **prescriptions** and **lab orders** are its own records in Desk, with a workflow, a lab job sheet and a report, **Lab orders to chase**. At Pay, a check refuses a lens line when the customer has no prescription of that kind in date, in words the cashier reads, and asks your service for only two fields of the prescription: its kind and **Valid until**.

![What the install will change, read before you consent](screenshots/01_install.png)

**Industries:** Optical

**When to use it:** a store keeps a record about its customers that decides whether some items may be sold, and the till must hold the rule while the record's contents stay in the retailer's iVendNext.

## Start from it

```bash
ivn new acme_optical --from s42
```

## What to change

What a partner usually changes:

- **The records:** a country's own prescription fields or a lab's own order fields, in the record types in `manifest.json` (`PP OPT Prescription`, `PP OPT Lab Order`).
- **The rule:** `optical.py`, for example a prescription that only warns, or a contact lens fitting that must be newer than a year.
- **The lab:** the order's workflow (*Ordered, Sent to lab, Ready to collect, Collected*) in `manifest.json`.
- **The mark:** `pp_opt_needs` on Item Group and Item (*Sold against a prescription*).
- **Your service's address:** `allowed_urls` in `manifest.json` names the sample's test address; write your own. `OPT_PREFIX` names the records for the service.

More: the [recipe](../../recipes/optical_prescriptions.md).

**The customer sets:** **Hours from UTC** in the settings record **Default** (the retailer's own day decides whether a prescription is in date), the mark on its lens item groups, the stores whose check is on, and the roles **PP OPT Optometrist** and **Sales User** for staff. Whoever chooses a lab needs a role that can see suppliers. Never enter a prescription on a walk-in customer: every walk-in sale would pass. A prescription is health-related personal data.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- Sell a prescription lens to a customer with no valid prescription; the till stops it at Pay.
- In Desk, enter the customer's prescription, then press Pay again.
- Close the till day when you are done.

## Versions

### 1.0.0

- First version in the kit: eye tests and lab jobs as the retailer's own records, and lenses refused at Pay without a prescription of their kind in date.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
