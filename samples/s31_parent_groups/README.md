# S31 — Parent item groups in coupons and promotions (`pp_pgx`)

*Start from this sample: `python3 tools/manifest/start.py s31_parent_groups --prefix "ACME PGX"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

A retailer sets up a coupon for *Supplements* and expects it to cover every supplement. But the till's coupon and promotion engines match an item's **own** item group exactly. A row naming the parent group *Supplements* matches only items placed directly in it, never those in *Supplements › Protein*.

This sample's service, outside the retailer's iVendNext, writes the parent out as its child groups and keeps it that way: when the coupon is saved, and when a new group is added under the parent. It is for an iVendNext Partner building for a retailer whose item groups are a tree.

**The doors it combines:** an outside app on the event feed, and the record API. **The limit:** a row appears a few seconds after the save, not in the same save. A promotion's buy and get rows are reported, never written out (below).

## What happens

| A person | The service |
|---|---|
| saves a **coupon** whose get rows name a parent group | adds one get row per child group (children, their children, …), each copying the parent row's quantity, discount and flags |
| saves a **promotion** whose exclusion rows name a parent group | adds one exclusion row per child group |
| adds an **item group** under a listed parent | adds it to every coupon and promotion that lists the parent |
| removes the parent row, or moves a group out from under it | removes the rows the service added that no listed parent covers any more, and only those (a child another listed parent still covers stays) |
| removes a child row the service added | leaves it removed: it is not added back while a listed parent covers it; it comes back if the parent leaves and is listed again |
| has added a child row of their own | leaves it alone, and never removes it |
| names a parent group in a **promotion's buy or get row** | reports it (*FLAG*), and changes nothing |

**Why not a promotion's buy and get rows.** Each buy row and each get row is counted and filled on its own. A child row there would add a condition to meet or a line to give, and change the offer. The report says so and asks the person to list the child groups, or to set the offer on the items.

**Coupons have no item-group exclusions** at this version: a coupon's exclusion rows name customer groups only.

## What the retailer does

1. **Install the manifest** (`manifest.json`). It declares only the feed registration *PP PGX Groups* (Coupon, Promotion Bonus Buys Master, Item Group). It installs switched off. From POS 2.1.0.667 the install also makes the app's own user, `pp_pgx@integration.invalid`, named on the feed, with the role **PP PGX Integration** (empty).
2. **Give the app's user its reads.** There is no user to make and no role to add: the app's own user holds **PP PGX Integration** alone, works through the API only and can never sign in to Desk. In *Role Permissions*, give that role read and write on Coupon and Promotion Bonus Buys Master, and read on Item Group, and tick each record type on the feed registration. For a service you run yourself, press *Generate Keys* on the app's user (User, API Access) and give the service its key.
3. **Run the service** where the partner runs services (`recipes/event_feed.md`):

   ```bash
   PGX_KEY=… PGX_SECRET=… python3 samples/s31_parent_groups/expander.py reconcile --base https://shop.example   # once, for what exists
   PGX_KEY=… PGX_SECRET=… python3 samples/s31_parent_groups/expander.py run --base https://shop.example --watch 15
   ```

**Where it shows.** On the coupon or promotion in Desk: the added rows, in their table. At the till: the coupon or the exclusion now covers the child groups' items.

**What leaves the retailer's iVendNext.** The service reads coupons, promotions and item groups, and writes coupon and promotion rows. With these rights its key can change any coupon or promotion.

## When the service is down or slow

- **Down:** nothing is written. Coupons keep their rows as they are, and a sale meanwhile gets the old rows. When the service is back, the feed's events are read in order. `reconcile` catches up everything at once.
- **A person saves while the service writes:** the service sends the `modified` it read, so iVendNext refuses its write. The event is retried on the next pass and reads the person's version. When an item group's save makes it go through every record, a refused record is rolled back alone (counted under `failed`) and the others are kept; that record catches up at its next save or at `reconcile`.
- **Any item group save goes through every coupon and promotion** (a read of each). That is cheap for a retailer with tens of them; a retailer with thousands should run `reconcile` on a schedule instead and leave Item Group off the feed registration.

## Ownership

The rows have no marker field, so the service keeps its own list of the rows it added (`state/pgx.sqlite`, table `ours`). It writes that list in the same transaction as the event.
- A row it did not add is a person's: never removed.
- A row it added that a person removed is recorded (table `removed`) and not added back.
- ⚠ **Keep the state file.** Lose it, and the service takes every child row it finds for a person's: it adds none twice, but it removes none when the parent goes.

## The files

| File | What |
|---|---|
| `manifest.json` | the feed registration, and nothing else |
| `groups.py` | the core: which rows a record needs, pure, no retailer |
| `expander.py` | the service: the feed, the record API, the ownership store |
| `tests/` | the core and the service against an in-memory stand-in · `canaries.py` |

## Run it

```bash
python3 -m unittest discover -s samples/s31_parent_groups/tests -p 'test_*.py'
python3 samples/s31_parent_groups/tests/canaries.py
python3 tools/check/check.py samples/s31_parent_groups
```

## Technical notes

### What was proven where

- **Laptop:** 13 tests and 9 canaries, each RED on its planted fault:
  - a person's row removed;
  - a person's row claimed as ours;
  - a promotion's buy row written out;
  - a removed row added back;
  - only the first level of children;
  - a child another listed parent covers dropped;
  - a group moved out of the tree kept;
  - a removed child never coming back;
  - one refused record rolling back the others.
- **Read at the product's head** (the engine, `development`):
  - the coupon engine matches `source_type == "Item Group" and source_key == item_group` on get rows;
  - the promotion engine excludes by an exact group set;
  - each promotion buy and get row is filled separately;
  - a coupon's exclusion rows offer *Customer Group* only.
- **Not run on a retailer's iVendNext.** The till applying a written-out coupon was not walked.

### Why this way (R6)

- *An outside app on the feed* — picked. About 260 lines (the core and the service; the tests are apart), and the retailer's records stay the retailer's.
- *A person listing child groups by hand* — the null option. It works, but a group added later is missed.
- *A change to the engines to match a group's descendants* — product work, and not needed: the kit composes it.
