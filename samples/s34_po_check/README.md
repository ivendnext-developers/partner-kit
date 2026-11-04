# S34 — Purchase orders checked by your ERP (a document check)

A distributor's ERP knows things iVendNext does not: which suppliers are on hold, and how much of its monthly purchasing budget the company has left. This app asks it before every purchase order is submitted, from Desk, an import or the API. A supplier on hold means the order is not submitted and stays a draft, with the ERP's reason. An order over the month's budget needs approval by a Purchase Manager. An order that is all clear is submitted with the ERP's own order number filled in.

**Industries:** every industry

## Start from it

```bash
ivn new acme_pocheck --from s34
```

## What to change

What a partner usually changes:

- **Your ERP:** `StandIn` in `erp.py` (and `erp_standin.json`) with a client of your ERP that has the same three methods: `supplier_hold`, `budget_left` and `order_number`.
- **Your service's address:** every `host.docker.internal` address in `manifest.json` (`allowed_urls` and the check's address) is the sample's test address; write your own.
- **The rules and words:** `on_check` in `po_check.py`.
- **When your service is down:** the order goes on and is flagged. A customer who wants nothing submitted unchecked sets *When the service is down* to refuse on the record.
- **The field:** `pp_poc_erp_number` in `manifest.json`; the service takes its prefix from `POC_PREFIX`.

More: the [recipe](../../recipes/document_check.md).

**The customer sets:** who may approve an order over the budget: the role **Purchase Manager**, given to those people.

## Run it

```bash
ivn check
ivn try
```

## Versions

### 0.1.1

- When the service is down an order goes on and is flagged, unless the customer chooses to refuse it.

### 0.1.0

- First version in the kit: purchase orders checked by your own back-office system, as a document check.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
- The README says to put your own service's address in the manifest before you install.
