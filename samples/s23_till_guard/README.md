# S23 — Till guard rules (a check before payment and a capture on scan, one app)

The common checks a shop wants before money is taken, in one app. Each rule is **off until the shop sets it**, in its own settings record in Desk:

| Rule | When | What the cashier sees |
|---|---|---|
| **No line at a placeholder price** (for example 0.01) | Pay | *"This sale can't be paid"* and *"Line 2: PEN-01 is priced 0.01 AED. Correct its price before the sale is paid."* A free line, priced 0, is never refused |
| **Most of one item on a line** | Pay | *"Line 1: 60 of WATER-24. The most on one line is 50."* Counted line by line: a promotion may split one item across two lines |
| **A large sale** | Pay | by default the cashier answers *"This sale is 5,000.00 AED or more. Has a manager agreed to it?"*; or, if the shop chooses `approve`, a manager who is not the cashier signs in on the till: *"Sales of 5,000.00 AED or more need a manager's approval."* |
| **Confirm a flagged item** | the scan | a beep and *"PEN-01: Check this item before it goes on the sale. Add it?"*; *No* leaves it off |

A return is judged only for the items it sells (an exchange rung without its sale), by the line rules; what it takes back never is, and the large-sale rule reads the total the customer pays (on an exchange, net of what it takes back). On a return the till's headline reads *This refund can't go ahead*. The recipe: [`recipes/till_guard.md`](../../recipes/till_guard.md).

## What the shop does

1. **Install the app** from the App library (or paste its manifest into **Retail Extension Package** in Desk), read what it will do and consent. The install adds the role `PP TGR Integration`, the two services and the feed registration, the services switched off. Nothing changes at the till yet.
2. **Make the record `Default`** of *PP TGR Settings* in Desk and fill in the rules it wants (0 or blank = off).
3. **Tick *Confirm at the till when scanned*** on each item to confirm.
4. **Make the app's integration user** (the [integration user recipe](../../recipes/integration_user.md)): tick *Is Desk User*, give it the role **PP TGR Integration** alone, generate its API key, choose it on the feed registration **PP TGR Guard**, then press **Connect again** on the app's record, which sends that user's key to the service. The service reads only the settings record with that key.
5. **For `approve` only:** first give the managers *May Approve a Partner's Check* on their Retail Permission and write access to *Retail Override Request* (the check refuses *May ask for a manager's approval* until someone other than the cashier can approve), then tick **May ask for a manager's approval** on the check. Without the tick an `approve` answer is not used and the sale goes on, flagged.
6. **Switch each service on:** open each service (*Retail Extension Subscription*), read what is sent, tick the consent, choose the POS Profiles, and switch it on.

**Where it shows.** The rules are Desk records the shop edits. At the till the cashier meets them at **Pay** (a refusal in the app's words, a question, or a manager's sign-in) and at the **scan** of a ticked item (a question). A sale the service could not check goes on and is flagged on *Sales to review*. A return is judged only for what it sells.

**What leaves the shop.** At **Pay**, the priced basket goes to the service's address: each line's item, group, quantity and amounts, the totals, the store and till, the cashier's user, the customer and their customer group, the coupons, the sale details the cashier captured and the payment methods offered; never a card. At the **scan** of a ticked item, the scanned line (item, group, quantity, unit, batch, serial, the code scanned), the sale's reference, the store, the till, the cashier and the customer go to the service's second address. The service reads the shop's settings record `Default` with the integration user's key, and nothing else. The manifest names those two addresses and no others; the shop sees both, and each service's consent, on the install screen and on the service's own record before it is switched on.

## What is in the folder

| File | What it is |
|---|---|
| `manifest.json` | the settings record type `PP TGR Settings`, a tick on Item (*Confirm at the till when scanned*), a feed registration (it names the app's one integration user), and two services: a `check` and a `capture` on scan filtered by that tick. Both install switched off and let the sale go on, flagged, when the service is down |
| `guard.py` | the pure core: the signature check (`verify`), the shape checks, the shop's rules (`settings_of`) and the answers (`on_check`, `on_scan`) |
| `service/app.py` | the service, standard library only: `POST /tgr/check`, `POST /tgr/scan`, `GET /health`, and the app template's handshake for many shops; one `handle` answers the web server and the function entry (`lambda_handler`) alike |
| `Dockerfile` · `app.json` | the settings file for hosting (`"runs": "function"`: on CitiXsys hosting it is a function, paid per call) and an image for your own server (built from the kit's root) |
| `tests/` | the rules, the service over the wire with signed calls (one shop and many), the shop's record read, every answer against the published contracts, the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## Run it

```bash
python3 -m unittest discover -s samples/s23_till_guard/tests -p 'test_*.py'
```
```bash
python3 samples/s23_till_guard/tests/canaries.py
```
```bash
python3 samples/s23_till_guard/service/app.py samples/s23_till_guard/service/.env.local
```

**Settings, one shop** (`service/.env.local`, never committed): `IVN_CHECK_SECRET` (handed back at install as `pp_tgr:sub:guard`), `IVN_SCAN_SECRET` (`pp_tgr:sub:on_scan`), `IVN_SHOP_URL`, `IVN_SHOP_KEY` (`<api key>:<api secret>` of the integration user), `PORT`. **Many shops** (the [app template](../../tools/app_template/README.md)'s handshake): `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`); each shop hands over the two secrets and its integration user's key when it connects. The shop makes that user after the install, so its key can only travel on a later connect (*Connect again*); until it does, the service answers 503 and the down answer applies (the sale goes on, flagged). `TGR_PREFIX` names the settings record type (default `PP TGR`).

## Technical notes

- **Each route takes only its own secret:** the check's call is checked with the check's secret, the scan's with the scan's. A site the app does not know gets 401.
- **The shop's rules are read, never written:** `GET /api/resource/<prefix> Settings/Default` with the integration user's key (1 s at most, inside the scan's 1.5 s), kept one minute. If the shop cannot be read, the last rules read stand in for up to ten minutes (kept by each running copy: on CitiXsys hosting a copy that has just started has none, so it answers 503 at once); after that the service answers 503 and the till applies the down answer (the sale goes on and is flagged on *Sales to review*). No record yet (the shop's 404 names that record) = every rule off; any other 404, such as a wrong prefix, is a 503.
- **What the service receives** is the contract's: the server's priced basket at Pay (`check/1`), the scanned line (`capture/1`). Never a card. It logs one line per call: the route, the status and the milliseconds, never the body.
- **The scan filter is the product's:** online, the server reads the item's tick at each scan, so an item ticked during the day is asked about at once; the service is called only for a ticked item. Offline the service is not called: the till keeps a start-of-day list of ticked items (at most 2,000) and applies the scan's down answer.
- **Offline,** the till does not call the service: each check's down answer applies and the sale is flagged when it syncs (chapter 9).
- **Amounts** are compared in the sale's own currency and its own digits (`currency_exponent`).

### What was proven where

- **Laptop:** the tests above (rules, signatures, the shop's record read, one shop and many, the contracts: 56 tests, and 1 more that replays a recorded bench run when one is given), 18 canaries each RED with its baseline passing, and the image built and run read-only (`/health`, an unknown shop 401, a bad key at connect 403).
- **Test bench** (2026-10-13, the iVendNext POS app at `87812e14`), **17 of 17** checks through the till's own calls as the cashier, over HTTPS, the service in one-shop mode reading the shop's `Default` record with the integration user's key: the install made both services switched off with `allow_and_flag`, the two secrets handed back once, the record type and the Item field; a line at 0.01 refused in the app's words and the card push refused before any money (0 sales booked); 51 of an item refused (*the most on one line is 50*); a 300.00 sale called a manager (approval from 250.00), the card push refused until a manager who is not the cashier approved in person (the cashier's own approval refused: *A cashier never approves their own sale.*), then one sale booked with the approver on the round; an ordinary sale booked; a ticked item's scan was answered `confirm` with the shop's own question; an unticked item's scan called nobody; uninstall left the schema as found; no POS day left open. **Not run on the bench:** the service down (the product's down answers for the check and the capture were proven with samples S18 and S20), many shops (the laptop tests), the ten-minute stand-in (the laptop tests), a real browser on the till's screens.
