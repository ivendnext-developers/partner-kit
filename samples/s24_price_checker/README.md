# S24 — Price-checker kiosk (a page on the store floor, priced by iVendNext)

A tablet or screen stands on the store floor. A customer scans an item and reads its name, its picture and its price: the store's price list price for one unit, in the scanned unit, found by iVendNext itself. Nobody signs in on the tablet, and the retailer switches each kiosk on and off in Desk. An item with no price says so and is never shown as free. Offers are not shown: the kiosk says *Any offer is worked out at the till.*

**Industries:** Grocery

## Start from it

```bash
ivn new acme_prices --from s24
```

## What to change

What a partner usually changes:

- **The kiosk record:** the record type `PP PRC Kiosk` in `manifest.json` (one record per screen, its name is its code; it takes its company, price list, currency, walk-in customer and store from the till profile chosen on it).
- **The sentences on the kiosk:** the answers drawn by `price.py`, and the page in `service/kiosk.html`, `kiosk.js` and `kiosk.css`.
- **How a scan is priced:** `price.py`. The service asks iVendNext for one unit on the store's price list and never sends a `rate`.
- **The record type's name:** `PRC_PREFIX` (default `PP PRC`).
- **Your own address:** `allowed_urls` in `manifest.json` names `https://prc.partner.example`; write your own.

More: the [recipe](../../recipes/price_checker.md).

**The customer sets:** one **PP PRC Kiosk** record per screen, with the store's till profile, and read on **PP PRC Kiosk** and on items and prices for the role **PP PRC Integration**. On the tablet, open the app's address with `#shop=` and the retailer's site, then `&kiosk=` and the record's name, in full screen. A barcode scanner connected as a keyboard scans into the page.

## Run it

```bash
ivn check
ivn try
```

## Versions

### 1.0.0

- First version in the kit: a price checker page on the shop floor, priced by iVendNext.
- It names its service's address, so a hosted copy is connected.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
