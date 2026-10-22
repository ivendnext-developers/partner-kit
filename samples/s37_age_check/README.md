# S37 — Age-restricted sale check (a capture on scan and a check before payment)

A shop that sells alcohol, tobacco, vapes, knives or some medicines must see the customer's ID before it sells them. This app gives each restricted item group (or item) its age. When the cashier scans a restricted item, the till shows the date of birth the customer must be born on or before. One tap records the check on the sale. At **Pay**, a restricted line the sale's check does not cover is refused:

| When | What the cashier sees |
|---|---|
| the scan of a restricted item | a sheet titled *Age check*: *"WHISKY-70: customers 18 or over. Born on or before 22 Oct 2008. Ask for ID if they look under 25."*, then *"This will be added to Single Malt 70 cl: PP AGE ID Checked: 18 or over"*. **Add with these details** puts the item on the sale and records the check; **Don't add it** leaves both off |
| a later restricted item of the same sale, needing that age or less | nothing: the sale was asked about already |
| **Pay**, a restricted line with no check on the sale (picked from a list, or *Don't add it* earlier) | *"This sale can't be paid"* and *"Line 2: WHISKY-70 is for customers 18 or over. See their ID, then enter 18 in Sale details, or take it off."* |
| **Pay**, a line needing more than the recorded check | *"Line 3: VAPE-01 is for customers 21 or over; the sale's ID check says 18. See their ID, then enter 21 in Sale details."* |

Everything else is allowed. A refund is never judged; an exchange is judged for what it sells. No date of birth or ID number is asked or kept: the sale records the age band the cashier confirmed. The recipe: [`recipes/age_check.md`](../../recipes/age_check.md).

## What the shop does

1. **Install the app** from the App library (or paste its manifest into **Retail Extension Package** in Desk), read what it will do and consent. The install adds the record type *PP AGE Settings*, a field *Customers must be at least this old* on Item Group and on Item, the sale detail *PP AGE ID Checked*, the role `PP AGE Integration`, the two services and the feed registration, the services switched off. Nothing changes at the till yet.
2. **Make the app's integration user** (the [integration user recipe](../../recipes/integration_user.md)): tick *Is Desk User*, give it the role **PP AGE Integration** alone and generate its API key. In *Role Permissions*, give that role a plain **read on Item Group and Item** (the app reads the group tree and the items' ages). Choose the user on the feed registration **PP AGE Check**, then press **Connect again** on the app's record, which sends that user's key to the service.
3. **Make the settings record `Default`** in *PP AGE Settings*: the shop's hours from UTC (`4` for Dubai, `3` for Nairobi; the date of birth shown is the shop's own day's), and, if the shop has the policy, *Ask for ID from anyone who looks under* (`25`).
4. **Set the ages:** on each restricted item group (*Alcohol* 18, *Vapes* 21), *Customers must be at least this old*; a group's age covers every group below it unless a group below sets its own. On an item whose age differs from its group's (a knife among kitchenware), the same field on the item.
5. **Name the restricted groups on the scan service:** open *Age check* in *Retail Extension Subscription* and add the groups to its settings, as `"item_groups": ["Alcohol", "Tobacco"]` beside `"event"` and `"item_field"` (the field already asks about items with their own age). The check at Pay reads every group's age itself, so a group left off this list is still caught at Pay.
6. **Switch both services on:** open *Age check* and *Age check at Pay*, read what each is sent, tick the consent, choose the POS Profiles and switch each on.

**Where it shows.** At the till, a sheet at the scan of a restricted item, and a refusal at **Pay**. The check is kept on the sale as the sale detail *PP AGE ID Checked*, under the basket's **🗒 Sale details**, where the cashier can also type it. In Desk, the settings record and the field on Item Group and Item. A scan or a sale the service could not check goes on and is flagged on *Sales to review*.

**What leaves the shop.** At the **scan** of a restricted item: the item, its group, quantity and unit, the code scanned, the sale's reference, the store, the till, the cashier's user and the customer. At **Pay**, the priced basket: each line's item, group, quantity and amounts, the totals, the store and till, the cashier's user, the customer, the sale details (the ID check, and any other detail the sale carries, such as a prescription number at a pharmacy) and the payment methods offered; never a card. The service reads the shop's settings, item groups and items with the integration user's key and writes nothing. The manifest names one address; the shop sees it, and each service's consent, on the install screen and on each service's own record before it is switched on.

## What is in the folder

| File | What it is |
|---|---|
| `manifest.json` | the record type `PP AGE Settings` (the record *Default*), a whole-number field on Item Group and on Item, the sale detail `PP AGE ID Checked` (never required), a feed registration naming the app's one integration user, a help address, and two services: a `capture` on scan filtered by the item field, and a `check`, both installed switched off; when the service is down the item goes on, or the sale is paid, flagged |
| `agecheck.py` | the pure core: the signature check (`verify`), the shape checks, each item's age (`age_of`), the date of birth (`born_by`), the answers (`on_scan`, `on_check`) and the sales already asked about (`Asked`) |
| `service/app.py` | the service, standard library only: `POST /age/scan`, `POST /age/check`, `GET /health`, and the app template's handshake for many shops; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the rules, the service over the wire with signed calls (one shop and many), the shop's reads against a stand-in shop, every answer against the published contracts, the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s37_age_check/tests -p 'test_*.py'
```
```bash
python3 samples/s37_age_check/tests/canaries.py
```
```bash
python3 samples/s37_age_check/service/app.py samples/s37_age_check/service/.env.local
```

**Settings, one shop** (`service/.env.local`, never committed): `IVN_SCAN_SECRET` (handed back at install as `pp_age:sub:scan`), `IVN_CHECK_SECRET` (`pp_age:sub:check`), `IVN_SHOP_URL`, `IVN_SHOP_KEY` (`<api key>:<api secret>` of the integration user), `PORT`. **Many shops** (the [app template](../../tools/app_template/README.md)'s handshake): `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`); each shop hands over the two secrets when it connects and its integration user's key on *Connect again*; until the key arrives the service answers 503 and the down answers apply. `AGE_PREFIX` names the record type, the fields and the sale detail (default `PP AGE`).

## Technical notes

- **An item's age** is its own *Customers must be at least this old* when above 0, else the nearest item group above it (itself first) that has one. So *Alcohol* 18 with *Beer* 16 below it sells beer at 16 and wine at 18.
- **The date of birth** is the shop's today, that many years back, by the settings' hours from UTC (29 February, in a year without one, is the 28th).
- **The scan's answer** is a `notice` with a sale detail: the till opens one sheet with the sentence and the value, and the value joins the sale only on *Add with these details*. A notice reaches POS build 2.0.0.654 and later; an older build refuses it as an unknown answer and applies the down answer (the item goes on, flagged), so the check at Pay is what holds there.
- **Asked once a sale:** the service remembers, for four hours, the highest age it asked about on each sale's reference, and does not ask again for that age or below. The till does not say what the cashier answered, so a sale asked about and then left off is caught at Pay. The reference is empty on a sale's first scan, so a sale whose first item is restricted is asked twice. Each running copy of the service remembers its own sales: on CitiXsys hosting a second copy may ask once more.
- **Two ages on one sale:** the till keeps one value per sale detail, so a later, lower ask replaces a higher one (a vape at 21 scanned first, then a beer at 18 asked by another running copy). Pay then names the higher age to enter.
- **The check at Pay** reads the sale detail's first whole number (*"18 or over"*, or *18* typed in Sale details) and refuses a line it sells whose age is higher, naming the highest age needed and its first line. It is the control: it runs whatever put the line on the sale (a scan, a list, a search), and the server holds its answer at every door that moves money.
- **What is read, and kept:** the settings record and the item groups, one minute per shop and per key; each item's own age, one minute. A refund reads nothing.
- **The shop cannot be read** (no answer, an error answer, a refused key, an answer cut short, not records, an item it does not return): 503, so the till applies the down answer (`allow_and_flag`: the item goes on, or the sale is paid, flagged on *Sales to review*). A shop that must never sell unchecked sets the scan service's down answer to `refuse` (a restricted item cannot be added while the service is down or the till is offline); the check's `refuse` would stop every sale, restricted or not. A redirect is never followed with the key.
- **Offline,** the till does not call the service: each down answer applies, and the scan's filter (the restricted groups and the items with their own age) travels with the till's start of day.
- **Bounds:** a manager's override of a refusal, restricted selling hours, the customer's date of birth or ID number, and a verified age kept on the customer are not in this version (each is a partner's version); the check does not run on a park to a till, a layaway deposit, an account collection or the Desk's own POS screen.
- It logs one line per call: the route, the status and the milliseconds, never the body.

### What was proven where

- **On the laptop:** the tests and canaries above (79 tests, 1 more that replays a recorded bench run when one is given; 44 canaries, each RED with its baseline passing).
- **On our test bench** (2026-10-22, the iVendNext POS app at `84185344` (the programme's own clone the bench mounts), the engine at `dc65d832`; the service in its one-shop form, reading the shop with a user holding only the app's role and a read on Item Group and Item; the shop's settings UTC+2, *ask for ID if they look under* 25; a group *Alcohol* at 18 with a whisky in a group below it, *Vapes* at 21, and a knife with its own age 18 in a group of none; the scan service naming Alcohol and Vapes), **11 of 11** through the till's own calls (the scan, the check, the card push, the booking) inside one day that was closed after: the whisky's scan answered with the date of birth and *18 or over*, on the sale's first scan and again once the sale had its reference · the same sale's next whisky not asked again · a vape on that sale asked at 21 · the knife asked by its own age · a plain item, and a whisky picked from a list, calling nobody · Pay on a whisky with no check refused in the app's words, the card push refused, no sale booked · a whisky with *18 or over* allowed and booked with the check on the sale · a whisky and a vape with *18 or over* refused naming the vape and 21 · the same basket with *21* typed in Sale details allowed and booked · a plain item booked with no check · the calls the till sent hold the published contracts. Before the scenario, each read the service makes was made as the app's user and none was refused. The install, the uninstall (the schema as found; the sale detail kept, switched off) and the rights put back were checked too, and no POS day was left open. **In a browser** on that bench: as a System Manager with Item Manager, the settings record (a change saved), the age on an item group and on an item (a change saved); at the till as the cashier (`/pos?frame=terminal`, 1440 wide), a whisky scanned showed the *Age check* sheet and went on with *Add with these details* (*Sale details · 1 recorded*), a vape picked from the catalogue went on with no question, Checkout was refused (*"Line 2: PPAGE-VAPE-01 is for customers 21 or over; the sale's ID check says 18. See their ID, then enter 21 in Sale details."*), and with 21 entered in Sale details the payment screen opened; the sale was voided.

## Make it your own

A partner's version of this app usually changes:
- **the rule:** a manager's override with a reason code, restricted selling hours, an ID scanner, or a customer's verified age kept on the customer record;
- **the words** the cashier reads (`agecheck.py`, `on_scan` and `on_check`).

The service takes its prefix from the setting `AGE_PREFIX`, so `python3 tools/manifest/rename.py samples/s37_age_check/manifest.json --prefix "ACME AGE"` renames the manifest and the hosting order, and the code needs no change for the name. A shop's ages and settings move to your copy with `tools/deploy/copy_records.py` ([Make one of our apps your own](../../recipes/make_it_your_own.md)).
