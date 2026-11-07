# S31 — Parent item groups in coupons and promotions (`pp_pgx`)

A retailer sets up a coupon for *Supplements* and expects it to cover every supplement, but the till's coupon and promotion engines match an item's own item group exactly. This sample's service, outside the retailer's iVendNext, writes the parent out as its child groups and keeps it that way: when the coupon or promotion is saved, and when a new group is added under the parent. The rows appear a few seconds after the save, not in the same save. A promotion's buy and get rows are reported, never written out.

**Industries:** Beauty and cosmetics

## Start from it

```bash
ivn new acme_groups --from s31
```

## What to change

What a partner usually changes:

- **Which rows a record needs:** `groups.py`, the core, which is pure and knows no retailer.
- **The feed and the writes:** `expander.py`, the service: the feed, the record API and the ownership store.
- **Which record types it watches:** the feed registration *PP PGX Groups* in `manifest.json` (Coupon, Promotion Bonus Buys Master, Item Group).
- **The state file:** `state/pgx.sqlite` lists the rows the service added. Keep it: without it the service takes a person's child rows for its own.

More: the [recipe](../../recipes/parent_groups.md).

**The app's role needs:** nothing from the retailer's administrator. The install makes the role *PP PGX Integration* and the app's own user, and gives the role **read on Item Group, Coupon and Promotion Bonus Buys Master**, the three record types the feed follows. The manifest's `role_rights` add write on Coupon and on Promotion Bonus Buys Master. **Needs POS build `2.1.0.691` or later:** on an earlier site the install warns `role_rights` as unknown and skips it, and gives the feed's user no read, so the events wait; the service's log says which record type was refused (`ivn logs`) ([What goes where](../../guide/07_manifests.md#what-goes-where)).

## Run it

```bash
ivn check
ivn try
```

Once, for what exists: `PGX_KEY=… PGX_SECRET=… python3 expander.py reconcile --base https://shop.example`.

## Versions

### 0.2.0

- Write on Coupon and on Promotion Bonus Buys Master moves into the manifest (`role_rights`), and the install gives the feed's user its reads, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 0.1.0

- First version in the kit: parent item groups in coupons and promotions.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
