# S33 — Click and collect (`pp_ccb`): a Desk board for web orders

A store's board for the web orders it must pick and hand over, in Desk, with no code of its own. A report lists the web orders still to pick; two fields on the delivery note record the hand-over, and the Delivery Note list filtered on one of them lists the orders waiting for their customer. Nothing leaves the retailer's iVendNext: no service, no outside address.

![The workspace: the line saying where the two lists are, and the two lists](screenshots/01_workspace.png)

**Industries:** every industry

**When to use it:** a retailer sells on the web and its customers collect in store, and you want every store to see the same lists without building a screen.

## Start from it

```bash
ivn new acme_collect --from s33
```

## What to change

What a partner usually changes:

- **The two fields on Delivery Note:** `pp_ccb_handed_over` and `pp_ccb_collected_by` in `custom_fields` in `manifest.json`.
- **The pick list:** the report's filters, and the roles it and the workspace open for (`roles`), in `reports` in `manifest.json`.
- **The workspace:** `workspaces` in `manifest.json`, the report, the two lists and the line that names the waiting filter.
- **The words Desk shows:** `translations` in `manifest.json` (*Click and collect*, *Web orders to pick*).

More: the [recipe](../../recipes/click_and_collect.md).

**The customer sets:** each store's warehouse in the pick list's filter, and the waiting list's filter (Status, Handed over No, POS Pickup Handed At not set, Set Source Warehouse, and Date on or after the day of install), saved once.

## Run it

```bash
ivn check
ivn try
```

## Versions

### 0.1.2

- The store manager (Retail Manager) and the stock clerk (Stock User) open the workspace and the report: the report names its roles (with Stock Manager, the sales desk's Sales User and Sales Manager, who read it before, and System Manager), and the workspace opens for the roles the manifest names. The workspace opens *Web orders to pick* itself, where its line said to search Desk for it.
- *Handed over* and *Collected by* sit on the delivery note's *Details* tab, under *Is Return*, where they were inside the folded *More Info*.
- Desk shows the workspace and the report as *Click and collect* and *Web orders to pick* through the manifest's `translations` block.

### 0.1.1

- The waiting list's filter also says *POS Pickup Handed At* is not set, so an order handed over at the till leaves it (the till writes that field, not *Handed over*); *shop* is *site* in the description.

### 0.1.0

- First version in the kit: a Desk board for click and collect web orders.
