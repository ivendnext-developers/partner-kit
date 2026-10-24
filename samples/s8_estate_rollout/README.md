# S8 — an estate roll-out as code: fifty stores and three regions from one file

Your whole estate — regions, prices, stores, tills, cashiers — written down in one file, and a script that makes iVendNext match it. This sample is for an iVendNext Partner or head office that sets up many stores and wants each change previewed, applied and checked, not clicked through store by store.

**When to use it:** you open or change stores in numbers, and need to see what will change before it does and prove afterwards that iVendNext matches the file.

**Door:** Configure

It is applied over the record API by a script, standard library only; written up as a recipe: `recipes/estate_rollout.md`.

## What the retailer does

This is for head office, or the partner who sets up its stores. Nothing is clicked through store by store: the estate is written down once, and a script makes iVendNext match it.

1. **Write the estate down.** Head office (or the partner) fills in `estate.json`: each **region** with its price list, a price for each item and one promotion; each **store** with its code, its region, its receipt format and its cashier; the manager of each region; the till profile new stores are copied from; the estate-wide switches and reason codes. Keep the file in your own repository and edit it by hand.
2. **Check iVendNext has what the file names.** The roles (this sample's file names *Retail Cashier* and *Retail Manager*, which are the retailer's own), the receipt formats and the items must already be in the retailer's iVendNext. The preview stops and names a blocker if one is missing.
3. **Preview with `plan`.** It lists every change the file would make, by store and by field, and writes nothing.
4. **Make iVendNext match with `apply`.** Use the key of a user who may edit all of it (the retailer's administrator). It makes, for each region, a **Price List** with its **Item Price** rows, one promotion limited to that region's stores, and a manager user with the manager role. For each store it makes a **Warehouse**, a till profile (**POS Profile**) copied from the reference profile with its warehouse, price list and receipt format set, and a cashier user with the cashier role and user permissions on that profile and warehouse. For the estate it sets the reason switch in **Retail Setting** and the reason codes. Running it again changes nothing.
5. **Check with `verify`** after a change, and whenever someone may have edited a store by hand. It is GREEN when iVendNext matches the file; RED names the store and the field.
6. **Enrol the till devices.** A user the roll-out makes has no password and no enrolled device; enrolling the till devices is a step of its own.
7. **To take the estate out, use `remove`.** A store with a booked sale is retired (disabled), not deleted, so its history stays.

**Where it shows.** In Desk, as the retailer's own records: the price lists and prices, the warehouses, the till profiles, the users, the promotions and the reason switch. There is no screen of its own: what `plan` and `verify` say is text the script prints. On the till, each store's cashier rings at that store's till profile, with its region's price list, promotion and receipt format. On the test site one sale was rung at one of the new stores; no till ran against the others.

**What leaves the retailer's iVendNext.** Nothing. The script reads and writes iVendNext over its record API, at the address you give it and with the key you give it, and sends nothing anywhere else. It keeps a `state/` folder on the machine it runs on, holding the reason switches' earlier values so `remove` can put them back. Treat the key as an administrator's.

## The files

| File | What |
|---|---|
| `estate.json` | the whole estate as data: 3 regions (a price list, prices and one promotion each), 51 stores (a warehouse, a till profile cloned from the reference profile, a receipt format, a cashier), managers, the reason switch and a reason code |
| `generate_estate.py` | writes `estate.json` (only so the sample can hold 51 stores without anyone typing them) |
| `rollout.py` | `plan` (what would change, nothing written) · `apply` (idempotent) · `verify` (reads everything back; RED on a hand edit or an orphan) · `remove` |
| `tests/test_s8.py` | 10 laptop tests against an in-memory stand-in |

## How to run it

```bash
cd samples/s8_estate_rollout
PP_BASE=https://shop.example PP_KEY=… PP_SECRET=… python3 rollout.py plan --estate estate.json
```

Swap `plan` for `apply`, `verify` or `remove` (below).

1. **`plan`** lists every change the file would make, by store and by field. It writes nothing.
2. **`apply`** makes those changes. Running it again changes nothing.
3. **`verify`** reads everything back and compares it with the file. It is GREEN when they match. It is RED when someone edited a record by hand, or a record the file does not name is left over, and it names the store and the field.
4. **`remove`** takes the estate out again.

There is no screenshot. Desk would show fifty-one stores as a list, but not what `plan` and `verify` say: **what differs from the file, by store and by field**. That is what an estate owner needs before and after a change.

## Before you copy it

- The script keeps its state in a `state/` folder.
- A store that a sale points at is retired (disabled), not deleted, when you remove the estate.
- It has been tried on a test site with one real store. The other stores were made for the test and taken out after. One sale was rung at one of them; no till ran against the others.

## Technical notes

### Why it is built this way

**Why this way (R6).** *Click each store through in Desk* — rejected: 51 stores, nothing to repeat or to check. *A manifest* — rejected: a manifest may not touch a retailer's own stores, users or prices. *One file, one diff engine for plan, apply and verify* (picked, ~330 lines): the same comparison prints the plan, drives the writes and judges the read-back, so they cannot disagree. State is kept in `state/` (excluded from the programme's `rsync --delete`).

### Bounds, stated

**Bench limits, stated.** The bench has one real store. The "51 stores" are warehouses and till profiles made for the test and taken out after; one sale is rung at one of them; no till runs against the others. A record a sale points at is retired, not deleted (set 1, F7).

### What was tested

| Where | What |
|---|---|
| `tests/test_s8.py` | 10 laptop tests against an in-memory stand-in |
| *our test bench's own run (not in the kit)* | the bench tests and the money-kit run with the estate applied |

What our test bench's run printed (2026-10-07, 33 of 33 checks; trimmed):

```text
PASS T1 plan exits 0 and lists every object the file names (3 price lists, 9 prices, 51 warehouses, 51 profiles, 3 promotions, 54 users, their permissions, 1 reason code)
PASS T1 …and wrote nothing: the shop's counts are the same after the plan
PASS T2 verify is GREEN: every object read back equals the file, no orphan
PASS T3 the second apply creates nothing, updates nothing, deletes nothing
PASS T4 the plan lists exactly two rows, both Item Price rows of the South price list
PASS T5 verify is RED and names the profile and the field the hand edit changed
PASS T5 apply repaired only that profile
PASS T7 …and ONLY that store is left: one profile, one warehouse (both disabled); the other 50 stores are deleted
```
