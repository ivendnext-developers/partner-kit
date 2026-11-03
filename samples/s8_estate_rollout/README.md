# S8 — an estate roll-out as code: fifty stores and three regions from one file

Your whole estate (regions, prices, stores, tills, cashiers) written down in one file, and a script that makes iVendNext match it. `plan` previews every change by store and field, `apply` makes them (running it again changes nothing), `verify` reads everything back and goes RED on a hand edit, and `remove` takes the estate out.

**What is in it:** `estate.json` (3 regions, 51 stores), `generate_estate.py` that writes it, and `rollout.py` with `plan`, `apply`, `verify` and `remove`.

**Industries:** every industry

**When to use it:** you open or change stores in numbers, and need to see what will change before it does and prove afterwards that iVendNext matches the file.

**Door:** Configure

## Start from it

**Set in Desk first: no app needed.** Write your estate in `estate.json` and run `rollout.py` with an administrator's key; it makes the price lists, warehouses, till profiles, users and promotions over the record API.

## What to change

What a partner usually changes:

- **The estate:** `regions` (each with its price list, prices and one promotion) and `stores` (code, region, receipt format, cashier) in `estate.json`; `generate_estate.py` writes the file if you would rather not type fifty stores.
- **The till profile new stores copy:** `reference_profile`.
- **The names:** `prefix`, `promotion_prefix` and `user_prefix`, and `roles` for the cashier and manager roles.
- **Estate-wide switches:** `settings` and `reasons`.

More: the [recipe](../../recipes/estate_rollout.md).

**The customer sets:** the roles (the sample names *Retail Cashier* and *Retail Manager*), the receipt formats and the items must already be in the retailer's iVendNext, or `plan` stops and names the blocker. Enrolling the till devices for the users it makes is a step of its own.

## Run it

```bash
PP_BASE=https://shop.example PP_KEY=… PP_SECRET=… python3 samples/s8_estate_rollout/rollout.py plan --estate samples/s8_estate_rollout/estate.json
python3 -m unittest discover -s samples/s8_estate_rollout/tests -p 'test_*.py'
```

Swap `plan` for `apply`, `verify` or `remove`. A store with a booked sale is retired, not deleted, by `remove`, and the script keeps the reason switches' earlier values in a `state/` folder so `remove` can put them back.

## Versions

### 1.0.0

- First version in the kit: fifty stores and three regions rolled out from one file.
