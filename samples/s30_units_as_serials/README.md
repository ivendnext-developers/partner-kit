# S30 — Units as serial numbers: each pack's printed code, tracked by iVendNext itself

Some retailers track every pack or handset by its own printed code. iVendNext already does this when the code is a serial number of an item that has both batches and serial numbers. This sample sets that up, moves an existing unit table onto it, and tells a lost unit from a sold one. No code runs in the retailer's iVendNext: the scripts run once on the administrator's computer, with the administrator's key.

**Industries:** Beauty and cosmetics, Electronics and phones, Pharmacy

**When to use it.** Each unit carries a code the retailer must check on every stock document, not only at the till. When the codes live in a table of the retailer's own and only the till needs to read them, a scan source is lighter: [S19](../s19_unit_codes/README.md).

## Start from it

**Copy by hand: not an app made here.** Copy `samples/s30_units_as_serials/` into your own repository and set `config.json` to the retailer's names.

## What to change

What a partner usually changes:

- **`config.json`:** the `company`, the `defective_warehouses` (the Defective store and its parent), the `items` (code, name, group, price) and, for a migration, the `migration` block (the old unit table, its `fields`, the `item_map` and `default_warehouse`).
- **Stock Settings:** `stock_settings` in `config.json`.
- **The report:** the results `units_report.py` names, in `units.py`.

More: the [recipe](../../recipes/units_as_serials.md).

In a package these rows go under `records` ([the manifest recipe](../../recipes/manifest.md)); the engine's settings (Retail Setting, Stock Settings), a Stock Entry and a Customer stay here.

**The customer sets:** a default Company (Setup > Global Defaults), the Defective store, the items and their prices, and, for a migration, which old item becomes which new one.

## Run it

```bash
PP_BASE=https://shop.example PP_KEY=<api key> PP_SECRET=<api secret> python3 samples/s30_units_as_serials/apply_config.py
PP_BASE=… PP_KEY=… PP_SECRET=… python3 samples/s30_units_as_serials/migrate.py
python3 -m unittest discover -s samples/s30_units_as_serials/tests -p 'test_*.py'
```

`migrate.py` is a dry run until you add `--apply`.

## Versions

### 1.0.0

- First version in the kit: each pack's printed code tracked as a serial number by iVendNext itself.
