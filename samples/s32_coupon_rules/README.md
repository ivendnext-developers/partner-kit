# S32 — Coupon rules (a check before payment that refuses a coupon the retailer restricted)

*Start from this sample: `python3 tools/manifest/start.py s32_coupon_rules --prefix "ACME CPN"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

Rules a retailer adds to its own coupons, checked when the cashier presses **Pay**. One rule record per coupon, written in Desk; each rule is **off until ticked or set**:

| Rule | What the cashier sees |
|---|---|
| **First purchase only** | *"This sale can't be paid"* and *"Coupon WELCOME10 is for a first purchase only; this customer has bought before. Remove it, or add the new customer."* The till always names a customer: before the cashier adds the new one, it is the walk-in customer, who has usually bought before |
| **Only for customers in one group** | *"Coupon STAFF15 is only for customers in Staff. Remove it, or add a customer in that group."* |

A coupon with no rule, or with its rule switched off, is never refused; a sale with no coupon is allowed without reading iVendNext. The cashier removes the coupon (or adds the new customer) and presses Pay again. The recipe: [`recipes/coupon_rules.md`](../../recipes/coupon_rules.md).

## What the retailer does

**Before you install:** every `host.docker.internal` address in `manifest.json` (in `allowed_urls`, and where the manifest calls it) is our test bench's own address for the sample's service, and it resolves only where Docker provides it. Replace it with your own service's address first, or iVendNext's calls never reach your service; if this manifest is already installed, raise its `version` and install it again ([the manifest recipe](../../recipes/manifest.md), step 6).

1. **Install the app** from the App library (or paste its manifest into **Retail Extension Package** in Desk), read what it will do and consent. The install adds the record type *PP CPN Rule*, the role `PP CPN Integration`, the check and the feed registration, the check switched off. Nothing changes at the till yet.
2. **Make the app's integration user** (the [integration user recipe](../../recipes/integration_user.md)): tick *Is Desk User*, give it the role **PP CPN Integration** alone and generate its API key. In *Role Permissions*, give that role **read on POS Invoice and Sales Invoice** (the first-purchase rule counts a customer's sales): a plain read, not *Only If Creator*, and give the user **no User Permissions**, or the count sees only part of a customer's sales and a returning customer can pass as new. Choose the user on the feed registration **PP CPN Rules**, then press **Connect again** on the app's record, which sends that user's key to the service.
3. **Write a rule for each coupon to restrict** in *PP CPN Rule*: the coupon, *First purchase only*, and/or *Only for customers in this group*.

   **If a rule names a customer group, stop cashiers moving a customer into it.** The till's edit sheet lets a cashier change a customer's group, and the retailer's cashier role can save customers: a cashier could move any customer into the coupon's group, and the coupon would pass. In *Customize Form* for *Customer*, set **Customer Group**'s *Perm Level* to 1, and in *Role Permissions* give level 1 *Write* on Customer only to the roles that may move customers (your managers). A cashier's change then leaves the group as it was (measured with [S47](../s47_customers_by_store/) on the programme's bench, run `pp-20261023T115256Z-45139`). Two things follow: a cashier can no longer give a new customer a group either: a customer created at the till takes the default customer group (Selling Settings), or none when none is set, and a manager sets the right one (measured on the programme's bench, run `pp-20261023T162435Z-43204`, with a default group and without), and the till still says *Saved* after a group change it dropped. Check the level 1 rows already there: Sales Master Manager has one by default, and no cashier's role may hold level 1 *Write*.

4. **Switch the check on:** open *Coupon rules* in *Retail Extension Subscription*, read what is sent, tick the consent, choose the POS Profiles, and switch it on.

**Where it shows.** The rules are Desk records the retailer edits. At the till the cashier meets them at **Pay**: a refusal in the app's words. A sale the service could not check goes on and is flagged on *Sales to review*.

**What leaves the retailer's iVendNext.** At **Pay**, the priced basket goes to the service's address: each line's item, group, quantity and amounts, the totals, the store and till, the cashier's user, the customer and their customer group, the coupons, the sale details the cashier captured and the payment methods offered; never a card. For a coupon with a rule, the service reads the retailer's rule records, and for a first-purchase coupon how many submitted sales that customer has, with the integration user's key. It writes nothing. The manifest names that one address; the retailer sees it, and the check's consent, on the install screen and on the check's own record before it is switched on.

## What is in the folder

| File | What it is |
|---|---|
| `manifest.json` | the record type `PP CPN Rule` (one per coupon, named by it), a feed registration (it names the app's one integration user), a help address, and one `check`, installed switched off; when the service is down the sale goes on, flagged |
| `coupons.py` | the pure core: the signature check (`verify`), the shape check, the retailer's rules (`rules_of`) and the answer (`on_check`) |
| `service/app.py` | the service, standard library only: `POST /cpn/check`, `GET /health`, and the app template's handshake for many retailers; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the rules, the service over the wire with signed calls (one retailer and many), iVendNext's reads against a stand-in iVendNext, every answer against the published contract, the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s32_coupon_rules/tests -p 'test_*.py'
```
```bash
python3 samples/s32_coupon_rules/tests/canaries.py
```
```bash
python3 samples/s32_coupon_rules/service/app.py samples/s32_coupon_rules/service/.env.local
```

**Settings, one retailer** (`service/.env.local`, never committed): `IVN_CHECK_SECRET` (handed back at install as `pp_cpn:sub:coupons`), `IVN_SHOP_URL`, `IVN_SHOP_KEY` (`<api key>:<api secret>` of the integration user), `PORT`. **Many retailers** (the [app template](../../tools/app_template/README.md)'s handshake): `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`); each retailer hands over the check's secret when it connects and its integration user's key on *Connect again*; until the key arrives the service answers 503 and the down answer applies. `CPN_PREFIX` names the rule record type (default `PP CPN`).

## Technical notes

- **What the check receives for a coupon:** `coupon_codes`, the names of the Coupon records on the sale (each one's `id`), never the code the cashier typed.
- **The rules are read, never written:** `GET /api/resource/<prefix> Rule`, every switched-on record, with the integration user's key, kept one minute per retailer and per key.
- **The first purchase is counted live** through the retailer's own `ivendnext_mpos.api.v1.get_count`, which checks the user's rights and its User Permissions: POS Invoices (`docstatus` 1, `is_return` 0) and Sales Invoices (the same and `is_consolidated` 0), both at once. The count is never kept. Group rules are judged first, because they read nothing.
- **iVendNext cannot be read** (no answer, an error answer other than 401 or 403, an answer cut short, not a list of records): 503, so the till applies the down answer. **iVendNext refuses the key** (401 or 403: a key withdrawn, a user disabled, a right not given): a sale with a coupon is refused in words that say so (a coupon with no rule still passes for up to a minute, while that copy keeps the rules it read), so a refused key never gives a restricted coupon unchecked. A redirect is never followed with the key.
- **The basket lock is the till's:** an allowed answer holds for exactly the basket checked; another line or coupon is refused before any money until the cashier presses Pay again.
- **Offline,** the till does not call the service: the down answer applies and the sale is flagged when it syncs.
- **Bounds:** the count is taken at the check, so a sale for the same customer booked after the check and before the money (at this till or another) is not seen; a customer group matches exactly; an order or layaway placement the till booked as a submitted POS Invoice counts (read in code, not run), a sale in another company on the same site counts, and a customer whose only document is an exchange's return, or whose only sale is offline and not yet synced, does not.
- **Where the check never runs:** a park to a till, a layaway deposit, an account collection (the check page, *Not in this version*) and the Desk's own POS screen: a restricted coupon rung there is neither refused nor flagged.
- **iVendNext's build:** `ivendnext_mpos.api.v1.get_count` exists on iVendNext POS since 2026-10-15; on an older build the count answers 404, read as iVendNext down, so the coupon passes, flagged. On CitiXsys hosting the first Pay after a quiet spell starts the function; past 3 s the down answer applies, flagged.
- It logs one line per call: the route, the status and the milliseconds, never the body.

### What was proven where

- **On the laptop:** the tests and canaries above.
- **On our test bench** (2026-10-18, the iVendNext POS app at `4c3f11b5`, the engine at `b26351df`; the service in its one-retailer form, reading iVendNext with a user holding only the app's role and a read on POS Invoice and Sales Invoice; two of the retailer's own coupons, 10% and 15% off), **8 of 8**, through the till's own calls inside one day that was closed after: a sale with no coupon allowed and booked · a first-purchase coupon for the walk-in customer refused in the app's words, the card push refused, no sale booked · the same coupon for a new customer allowed, booked at 90.00 of 100.00 with the coupon on the sale · that customer's next sale with it refused (the sale just booked counted live) · a group coupon for a customer outside the group refused, nothing booked · for a customer in it allowed, booked at 85.00 · after an allowed check, a second unit, another customer or another coupon each refused before any money, and Pay again asked the service again · the service received each coupon by its record's name, never the code typed. The install, the uninstall (the schema as found) and the rights put back were checked too, and no POS day was left open. **Not run on the bench:** a cash booking of a refused basket (the bench's day has no drawer, so the till refuses cash before the check's door; read in the till's code, the door refuses it), many retailers (the laptop tests), offline.
