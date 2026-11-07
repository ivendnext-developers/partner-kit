# S26 — Derived price lists (a price list worked out from another, kept in step)

One price list worked out from another: the selling list is 1.5 times the buying list, or the wholesale list is 0.9 of the retail list. When someone changes a price on the source list, the app changes the derived price within seconds. Nothing changes at the till: the cashier sells at the list's price as before. A price a person set on the target list is kept and listed, never overwritten. A deleted source price ends its derived price from yesterday, and a rule's target can be another rule's source.

**Industries:** every industry

## Start from it

```bash
ivn new acme_prices --from s26
```

## What to change

What a partner usually changes:

- the rule's numbers, on the `PP DPL Rule` record type in `manifest.json`: `factor`, `offset`, `rounding_step`, `rounding`, `floor`, `decimal_places`;
- the formula and its rounding, in `prices.py` (source × factor + amount, rounded to the step, never below the floor);
- how the service follows the feed and writes prices, in `sync.py`.

More: the [recipe](../../recipes/derived_price_lists.md).

**The customer sets:** the rules (the source and target lists, the factor and the rest) and the decimal places to match its currency. The rights of the role **PP DPL Integration** are the install's and the manifest's, not the retailer's: the install gives it read on Item Price, the record type the feed follows, and `role_rights` give read on Price List and create and write on Item Price. With these rights the app's key can change any item price, so only the app's own user holds the role. **Needs POS build `2.1.0.691` or later:** on an earlier site the install warns `role_rights` as unknown and skips it, and gives the feed's user no read, so the events wait; the service's log says which record type was refused (`ivn logs`).

## Run it

```bash
ivn check
ivn try
```

The service runs on your server with the integration user's key in the environment: `sync.py run --base <site> --state state/dpl.sqlite --watch 5`, and `sync.py reconcile` reads every target price against its source and changes nothing.

## Versions

### 0.2.0

- The role's rights move into the manifest (`role_rights`), and the install gives the feed's user its read on Item Price, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 0.1.1

- First version in the kit: a price list worked out from another and kept in step.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
