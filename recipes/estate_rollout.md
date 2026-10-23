# Set up fifty stores from one file — the estate roll-out recipe

You describe a whole chain of stores in one file, and a small tool makes iVendNext match it: price lists, promotions, permissions and receipt formats, store by store. This recipe is for a retailer with **many stores and several regions** that must be set up the same way, changed together, and checked afterwards — or for the iVendNext Partner or team serving that retailer.

**Reference implementation:** `samples/s8_estate_rollout/` (`estate.json` is the whole estate; `rollout.py` has four verbs; standard library only). It reuses the pieces of two other recipes — the receipt format by configuration (`recipes/receipt_format.md`), the reason switches (`recipes/configure_no_code.md`).

**When to use it.** When more than a handful of stores must carry the same set-up, and every change must reach all of them and be checked.

## Steps

1. **Write the file.** `estate.json` names: **regions** (a price list, a price per item, one promotion, a manager each) · **stores** (a code, a region, a receipt format, a cashier) · the reference profile new till profiles are cloned from · the **warehouse defaults** every store carries · estate-wide switches and reason codes. A real customer keeps it in their own repository and edits it by hand; `generate_estate.py` only writes 51 stores for the sample.

   | Per… | The roll-out makes |
   |---|---|
   | region | a **Price List** and its **Item Prices** · one **promotion**, limited to that region's stores · a manager user with the manager role |
   | store | a **Warehouse** (with the outlet defaults below) · a **till profile** cloned from the reference profile (its warehouse, price list and receipt format set) · a cashier **user** with the cashier role and **user permissions** on that profile and warehouse |
   | estate | the reason switch(es) in Retail Setting and the reason codes |

2. **See what would change: `plan`.** It lists what `apply` would change, object by object and field by field (`update POS Profile: PP EST N005 {"print_format": ["Gift Receipt", "mPOS Receipt"]}`). It **writes nothing**. It names a **blocker** (a receipt format, item or role iVendNext does not have), and `apply` refuses until it is gone.

   ```bash
   PP_BASE=https://shop.example PP_KEY=… PP_SECRET=… python3 samples/s8_estate_rollout/rollout.py plan|apply|verify|remove --estate estate.json
   ```

3. **Make iVendNext match the file: `apply`.** It is idempotent: a second `apply` creates, updates and deletes nothing.

4. **Check it: `verify`.** It reads everything back and compares it with the file. It exits 1 and names **every difference** if a store was edited by hand, or if something with the estate's prefix is **not in the file** (an orphan: a warehouse, a profile, a price list, an **Item Price** — one dropped from the file, or a second row for the same item and list —, a promotion, a user or a reason code).

5. **Take it out: `remove`.** It removes the estate in reverse order. A record a booked sale points at **cannot be deleted** (iVendNext keeps its history): it is **retired** (disabled) and the line says so. A later `apply` switches it back on instead of making it twice. A record that can be neither deleted nor retired is listed under `kept`, never skipped silently.

One comparison drives `plan`, `apply` and `verify`, so the plan, the writes and the read-back cannot disagree.

## What iVendNext requires (and the file carries)

- ⚠ **A store's outlet defaults live on its WAREHOUSE, not its profile.** iVendNext derives a profile's price list **from its warehouse** (`custom_selling_price_list`) and **refuses to save a profile whose warehouse has none** (*"Please define selling price in warehouse …"*). The till then refuses a store with no **cash customer** on the warehouse (*"No cash customer on warehouse …"*). The reference store also carries an **item tax template** and a **company currency** on its warehouse. `estate.json` carries all of them under `warehouse_defaults`, and `verify` checks them.
- A till profile is **cloned** from the reference profile (payments, interface profile, write-off accounts, tax template); only its warehouse, price list, receipt format and `disabled` are the estate's. Its name is given with `__newname`.
- **The till rings at the outlet its user is bound to** (a user default), not at the profile of the day it opened. A store a roll-out made is therefore reached by binding the user to it — which is what assigning a cashier means in a real store.

## Limits to know before you start

- A user the roll-out creates has no password and no enrolled device. Enrolling the till devices is a step of its own.
- `verify` checks only the fields the file owns. A field it does not own can be edited by hand and `verify` will not see it.
- The file is the whole truth for user permissions: `apply` deletes any an estate user holds that the file does not name. Any other record with the prefix is only *reported* as an orphan, never deleted.
- Roles are assigned, not created: the roles must already exist (`plan` blocks otherwise).
- `remove` retires but never un-sells: a retired store stays in the retailer's history.
- Change the prefixes in the file together with the names.

## Technical notes

### What was measured

The retailer's requirements above were measured on our test bench (the engine derives a profile's price list from its warehouse); the file now carries them.

### Proven on the bench

The recipe is **proven** on our test bench.

- `plan`: **writes nothing** (proven: the retailer's counts are equal before and after).
- `apply`: **Idempotent: proven** — the second `apply` created, updated and deleted nothing (`applied = 0`), and no profile's, warehouse's or Item Price's modified time moved (the other kinds' times were not snapshotted).
- `verify`: **Exit 1 and every difference by name**. Proven on a hand edit and on an orphan warehouse; an orphan Item Price is proven by the laptop tests only.
- **Plan on an empty estate** lists 3 price lists, 9 prices, 51 warehouses, 51 profiles, 3 promotions, 54 users, 153 permissions and a reason code, plus the switch; **writes nothing**.
- **Apply** creates them; **verify** is GREEN; **apply again** changes nothing.
- **Change one region's price:** the plan lists exactly the two Item Price rows of that region; after `apply` only those two records were modified (profiles, warehouses, the other prices untouched); `verify` against the **old** file is RED and names them.
- **An edit by hand** (one store's receipt format): `verify` RED naming the profile and the field; the plan lists that one row; `apply` repairs only it. **An orphan warehouse:** named by `verify`.
- **A promoted sale at a roll-out store:** the same basket, promotion off then on, is 198.00 then 178.20 (10% less); **the booked sale equals the till's preview**; the retailer's own profile, same basket, has **no discount** — the promotion reaches the roll-out stores only (its sources are the stores' warehouses).
- **Remove:** nothing live left (no enabled profile, warehouse, user or active promotion); the reason switch is back to its earlier value; the store a sale was rung at is retired, not deleted.
- **The money kit** with the estate applied (51 stores, their promotions limited to the roll-out stores): **GREEN, 67 of 67 matched**, 32 with a discount, no POS day left open — the retailer's own recorded baskets are untouched by the roll-out.

### Bounds, stated

- **The bench has one real store.** The "51 stores" are warehouses and till profiles made for the test; one sale was rung at one of them; no till runs against the others, and **no sale was rung at a store of another region** (the promotion's limit to one region's stores is proven by the retailer's own store not being reached, and by `verify` reading the source list, not by a second region's sale).
- A user created through the roll-out has **no password and no enrolled device**: enrolling the till devices is a step of its own.
- **`verify` reads the fields the file owns** (a store's warehouse, price list, format, state; a price's rate; a promotion's switch, percentage and sources; a user's enabled flag and managed roles; the user permissions). A field it does not own can be edited by hand without a finding.
- **Roles and user permissions: laptop-tested only** (a hand-changed role and a stray permission are named by `verify` and repaired by `apply`; no bench run exercised them). Permissions: `User Permission` rows an estate user holds that the file does not name are **deleted by `apply`** (the file is the whole truth for them); any other record with the prefix is only *reported* as an orphan, never deleted.
- Roles are assigned, not created: the roles must exist (`plan` blocks otherwise). A role's own permissions are the retailer's.
- `remove` retires but never un-sells: a retired store stays in the retailer's history. A record that can be neither deleted nor retired is listed under `kept`, never skipped silently.
- The prefixes orphan detection and `remove` look for are in the file (`prefix`, `promotion_prefix`, `user_prefix`); change them together with the names.
