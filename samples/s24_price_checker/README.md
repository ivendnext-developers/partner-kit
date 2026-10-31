# S24 — Price-checker kiosk (a page on the shop floor, priced by iVendNext)

*Start from this sample: `python3 tools/manifest/start.py s24_price_checker --prefix "ACME PRC"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

**Industries:** Grocery

## What the retailer does

A tablet or screen stands on the shop floor. A customer scans an item and reads its name, its picture and its **price**. The price is the retailer's own: the store's price list price for one unit, in the scanned unit, found and converted by iVendNext itself (the same price list lookup the till starts a sale from). Nobody signs in on the tablet; the retailer switches each kiosk on and off in Desk.

| On the kiosk | When |
|---|---|
| name, picture, **Price** and *Any offer is worked out at the till.* | the scan finds an item with a price on the store's list |
| *"We could not find this item. Please ask a member of staff."* | nothing matches the scan |
| *"This item has no price here. Please ask a member of staff."* | no price on the store's list (never shown as free) |
| *"This item is not on sale. Please ask a member of staff."* | iVendNext refuses to price it (disabled, past its end of life, a template) |
| *"This kiosk is not set up. Please ask a member of staff."* | the kiosk's record is missing or switched off |
| *"Price checks are not available right now."* | iVendNext or the service cannot be reached |

**Offers are not shown.** On iVendNext a selling offer is a promotion, and the engine works promotions out on a whole sale at the till (it refuses a selling price rule), so a one-unit price check cannot ask for one; the kiosk says *Any offer is worked out at the till.* under every price. It never shows more than the store's list price. The recipe: [`recipes/price_checker.md`](../../recipes/price_checker.md).

| File | What it is |
|---|---|
| `manifest.json` | the record type `PP PRC Kiosk` (one record per screen; its name is a random code; it takes its company, price list, currency, walk-in customer and store from the till profile chosen on it), its help address, and a feed registration that names the app's one integration user. Nothing else: no till key, no check, no field on the retailer's own records |
| `price.py` | the pure core: the kiosk's code and scan, the kiosk's date, the Kiosk record, the arguments for the retailer's line pricer (no price rule, never a `rate`), and the answer |
| `service/app.py` | the service, standard library only: the page (`GET /`), `POST /prc/price`, `GET /health`, and the app template's handshake for many retailers; on CitiXsys hosting it runs as a function (`lambda_handler`) |
| `service/kiosk.html` · `kiosk.js` · `kiosk.css` | the kiosk's page: a scan box that keeps the focus, the answer drawn as text only, cleared after 20 seconds |
| `Dockerfile` · `app.json` | the image for your own server, and the settings file for hosting (a function, paid per call) |
| `tests/` | the core, the service over the wire (one retailer and many, the function entry, the three reads of iVendNext against a stand-in) and the manifest; `canaries.py` breaks each guarded rule and expects its test to fail |

## What the retailer does to set it up

0. **Before install:** make the role **PP Integration** if iVendNext does not have it. The install makes an app's own roles only when they are named under its prefix (`PP PRC …`); `PP Integration` is the kit's shared role, so iVendNext makes it.
1. Give the app's user its reads. From POS 2.1.0.667 the install made the app's own user, `pp_prc@integration.invalid`, and named it on *PP PRC Kiosk feed*. It holds one role, **PP PRC Integration**, works through the API only and can never sign in to Desk; nobody can give it another role, so the shared **PP Integration** of step 0 cannot be given to it. In *Role Permissions*, give **PP PRC Integration** read on **PP PRC Kiosk** and the reads iVendNext's barcode lookup and line pricer need on items and prices. The service reads with the user's key and writes nothing. A service for many retailers is handed the key by the retailer's site itself (below); for one retailer, press *Generate Keys* on that user (User, API Access) and put the key in the settings.
2. Make one **PP PRC Kiosk** record per screen: where it stands, and the store's till profile. The record's name is the kiosk's code.
3. On the tablet, open the app's address with `#shop=` and the retailer's site, then `&kiosk=` and the record's name, in full screen. A barcode scanner connected to the tablet as a keyboard (USB or Bluetooth) scans into the page.

## Run it

```bash
python3 -m unittest discover -s samples/s24_price_checker/tests -p 'test_*.py'
```
```bash
python3 samples/s24_price_checker/tests/canaries.py
```
```bash
python3 samples/s24_price_checker/service/app.py samples/s24_price_checker/service/.env.local
```

**Settings, one retailer** (`service/.env.local`, never committed): `IVN_SHOP_URL`, `IVN_SHOP_KEY` (`api key:api secret` of the integration user), `PORT`. **Many retailers** (the [app template](../../tools/app_template/README.md)'s handshake): `IVN_LIBRARY_APP` and a store (`IVN_SHOPS_TABLE` on CitiXsys hosting, else `IVN_SHOPS_FILE`); each retailer's site hands over the key of the app's own user when it connects, after the install or an update (*Connect again* is only for when the site could not reach the app, or a key was lost or changed), and each kiosk's call names its retailer. Until the key arrives, the kiosk says it is not set up. The site connects only to the one `*.ivendnext.app` address in the manifest's `allowed_urls` (the POS release that carries the hosted handshake, train T10); the sample names `https://prc.partner.example`, so write your own. `PRC_PREFIX` names the Kiosk record type (default `PP PRC`).

## Technical notes

- **How the page finds its retailer.** A partner page (chapter 9) is opened by the till and its call names no retailer. A kiosk is not opened by the till: it is a browser, so its own address names its retailer (`#shop=`) and its kiosk (`&kiosk=`). The part after `#` never reaches a server log. The service answers only for a retailer that connected and a Kiosk record of that code that is switched on.
- **Only for public, read-only screens.** The address is the only key, so this pattern fits what anyone in the retailer's iVendNext could see (a price). A member's balance, an order or anything that writes needs a sign-in.
- **The code is the framework's random name** (10 characters of base 32, about 50 bits), made by iVendNext. Whoever has a kiosk's address can check prices at that store, as anyone standing in it can. Switching the Kiosk off stops its address within a minute: the record is read with the app's key and kept one minute. A run of unknown codes (20 a minute, per copy of the service) stops being looked up in the retailer's iVendNext; a code the retailer has made is always looked up, so guesses cannot lock a real kiosk out of a copy that has seen it. ⚠ Both the count and the codes seen are kept in each copy's memory. On CitiXsys hosting S24 runs as a function, whose copies start and stop on their own: a new copy has seen no kiosk, so someone who knows a retailer's site address and keeps sending made-up codes can make that retailer's real kiosks say *Please wait a moment* while it lasts. The same count tells them, by its *Please wait*, that the site uses the app. Keep both in your shops store if that matters to your customers. Whoever holds a real kiosk's address can check as often as they like, and each check is two calls to iVendNext.
- **The price is the retailer's own.** For each scan the service makes two calls with the app's key, both whitelisted calls of iVendNext: `ivendnext_mpos.api.v1.scan_barcode` (a barcode, a serial number or a batch; the same lookup the till's scan composes) and `ivendnext_mpos.api.v1.get_item_details`, the retailer's line pricer, for one unit, in the scanned unit (a price in the stock unit is converted), on the store's price list, for its walk-in customer (a price row for that customer first), on the kiosk's own date (within a day of the service's), with no price rule. ⛔ The service never sends a `rate`: given one, the pricer may write a price row when the retailer's *auto-insert price* setting is on.
- **What it sends outside:** the retailer's site sends only the hosted handshake: its App library key, its address and the integration user's key, at install, update, *Finish* and *Connect again*. The service reads the Kiosk record and iVendNext's two answers for each scan; the pricer's answer carries the item's details (its name, unit, picture, price, description, group, brand and accounts) and the store's stock figures, of which the kiosk shows the name, unit, picture and price and the service keeps none. The kiosk sends the service the scanned text, the kiosk's code, the retailer's address and the tablet's date. It logs one line per call: the route, the status and the milliseconds, never the scan or the code.
- **The page** is served with a content policy that allows only the app's own script and style, and pictures from any https address; it draws every answer as text. The service passes a picture only when it is one of the retailer's public files (`/files/…`), and builds its address from the retailer's own.
- **Bounds:** offers are not shown (above); a walk-in customer whose customer group has its own price list is priced on the store's list; a typed item code is not looked up (1.0); the price is shown in the till profile's currency, converted by the retailer's own exchange rate when its price list is in another (read in the engine's pricer, not run on our bench); the kiosk is online only.

### What was proven where

- **Laptop:** the tests above (53) and 24 canaries, each RED with its baseline passing. The page in a real browser (the laptop, 2026-10-15), against a stand-in iVendNext: a scanned barcode followed by Enter showed the item, its unit and *ZAR 12.50* with the offers line; an item with no price and an unknown barcode showed their sentences; an address with no kiosk said *not set up*; the scan box kept the focus throughout.
- **Test bench** (2026-10-15, the iVendNext POS app at `e149dce4`; run `pp-20261015T045526Z-22519`, on the reviewed code), **20 of 20** checks, the service in one-retailer mode reading the bench iVendNext with the integration user's key: the install made the Kiosk record type with random names and its help address, and the feed registration, with no service and no secret; a Kiosk took its company, price list, currency, walk-in customer and store from the till profile; the page was served with its content policy; two items scanned by barcode showed **12.50** and **7.25**, the same as the till's own price for one of each (`api.mpos_cart.recompute`, in a day opened and closed); an item with no price said *no price here*; a disabled item said *not on sale*; an unknown barcode and a typed item code said *could not find*; a kiosk switched off, and a code the retailer never made, said *not set up* (the retailer's real 404 names the record); price rows, price rules, items and kiosks counted the same before and after the scans (the bench's *auto-insert price* setting is off, so this cannot see the one write the pricer can make; that the service never sends a `rate` is proven by the laptop tests); switched off in Desk, the kiosk said *not set up* after the service's minute; the service's log carried no scan and no code; uninstall left the schema as found; no POS day left open. **Not run on the bench:** many retailers (the laptop tests; the product sends the handshake since train T10), iVendNext down (the laptop tests), a promotion (not shown, by design).

## Versions

### 1.0.0

- First version in the kit: a price checker page on the shop floor, priced by iVendNext.
- It names its service's address, so a hosted copy is connected.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
