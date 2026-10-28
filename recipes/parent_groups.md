# A coupon or promotion for a parent item group — the recipe

A retailer sets up a coupon for *Supplements* and expects it to cover every supplement. The till's coupon and promotion engines match an item's **own** item group exactly, so a row naming the parent *Supplements* never matches an item in *Supplements > Protein*. This recipe is for an iVendNext Partner building for a retailer whose item groups are a tree.

**Reference implementation:** `samples/s31_parent_groups/`: a manifest with one event-feed registration, and a small service that writes the parent group out as its child groups and keeps it that way.

**The rules, here.** Your service runs outside the retailer's iVendNext. It reads the feed, and writes only the rows it adds to coupons and promotions, through the record API, with its own key and rights. A row appears a few seconds after the save, not in the same save.

## What the retailer sees

| A person | The service |
|---|---|
| saves a **coupon** whose get rows name a parent group | adds a get row per child group (children, their children, and so on), each copying the parent row's quantity, discount and flags |
| saves a **promotion** whose exclusion rows name a parent group | adds an exclusion row per child group |
| adds an **item group** under a listed parent | adds it to every coupon and promotion that lists the parent |
| removes the parent row, or moves a group out from under it | removes the rows it added that no listed parent covers any more, and only those |
| removes a child row the service added | leaves it removed while the parent is listed |
| names a parent group in a **promotion's buy or get row** | reports it, and changes nothing: each buy and get row is counted on its own, so a child row there would change the offer |

## Steps

1. **Declare the feed registration in your manifest** (S31's `manifest.json`): one registration on Coupon, Promotion Bonus Buys Master and Item Group. It installs switched off.
2. **Make the service's user** ([the integration user recipe](integration_user.md)): a role with read and write on Coupon and Promotion Bonus Buys Master and read on Item Group, a user made for the app alone, and its API key. iVendNext support sets that user on the registration; the retailer's administrator switches it on.
3. **Run the service** where you run services ([the event feed recipe](event_feed.md)): `reconcile` once for what exists, then `run`, which reads the feed's events in order.
4. **Write with the row as read.** Send the `modified` you read, so iVendNext refuses your write when a person saved meanwhile; the event is retried on the next pass and reads the person's version.
5. **Keep a list of the rows you added**, in the same transaction as the event (S31 keeps it in its own state file). The rows carry no marker field: a row not on your list is a person's, and is never removed; a row you added that a person removed is recorded and not added back.
6. **Test it** with S31's tests and canaries, then on a sandbox: install, the user and its rights, the switch, then a coupon on a parent group.

## Limits to tell the customer

- **A row appears a few seconds after the save,** not in the same save. A sale in between gets the old rows.
- **A promotion's buy and get rows are reported, never changed.** List the child groups, or set the offer on the items.
- **A coupon has no item-group exclusions** at this version: its exclusion rows name customer groups only.
- **While the service is down,** nothing is written; when it is back, the feed's events are read in order, and `reconcile` catches up everything at once.
- **Every item group save reads every coupon and promotion.** Cheap for tens of them; with thousands, run `reconcile` on a schedule and leave Item Group off the registration.
- **Keep the service's state.** Lose it, and the service takes every child row for a person's: it adds none twice, but removes none when the parent goes.
- **Not walked on a till:** a sale applying a written-out coupon (S31's README, *What was proven where*).
