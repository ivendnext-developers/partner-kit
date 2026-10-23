# A price checker on the shop floor (a kiosk page your app serves) — the recipe

A retailer wants a screen on its floor where a customer scans an item and reads its price, without asking a cashier. iVendNext's own guide calls this *a genuinely different screen*, a separate application, not a till key. This recipe builds it as **a page your app serves**, priced **by iVendNext itself** for each scan. It is for an iVendNext developer who has made an outside app before ([chapter 5](../guide/05_outside_apps_and_event_feed.md)).

**Reference implementation:** `samples/s24_price_checker/` — *Price-checker kiosk*.

**When to use it.** A screen on the shop floor that nobody signs in to, that only **reads**, and that shows only what anyone standing in the retailer's iVendNext could see: a price checker, an *is it in stock* screen. ⛔ **Not** for a member's balance, a customer's order, a staff clock-in or anything that writes: whoever holds the address can use it, so those need a sign-in ([recipe](sign_in.md)). For a screen the cashier opens on the till, use a partner page ([recipe](partner_page.md)): the till opens it and hands it the sale.

## Steps

1. **Declare one record per screen in your manifest** (`samples/s24_price_checker/manifest.json`): a record type `<PREFIX> Kiosk` named by the framework's random name (`"autoname": "hash"`), so each record's name is a code nobody can guess; a link to the store's till profile, and read-only fields that fetch what you need from it (`fetch_from`: company, price list, currency, walk-in customer, store). Give **System Manager** the rights to edit it and your integration role **read only**. Name that role under your prefix (`<PREFIX> Integration`) and the install makes it; a role outside your prefix must exist on the retailer's iVendNext before the install, which refuses a permission row for a role iVendNext lacks (the sample uses the kit's shared `PP Integration`, so its iVendNext makes it first). Add a feed registration naming the record type, so the retailer chooses your integration user there, and a `documentation` property setter on the record type pointing at your help page.

2. **Serve the page from your app, and let its address name the retailer.** A partner page is opened by the till, and its call names no retailer. A kiosk is a browser: its address carries the retailer and the screen after a `#`, which never reaches a server log:

   ```text
   https://your.app/#shop=shop-a.example.com&kiosk=k3v9q0abcd
   ```

   The page sends both with each scan to your own service (`POST /prc/price`, same origin). It holds no key and signs nothing. Serve it with a content policy that allows only your own script and style (`default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src https:`), keep the script in its own file, and draw every answer with `textContent`.

3. **Answer only for a retailer you know and a screen it has switched on.** Your service finds the retailer among those that connected (the [app template](../tools/app_template/README.md)'s handshake, keyed by site; or the one retailer it is set up for), reads the screen's record with **that retailer's** key, and answers only when it exists and is switched on. Keep the record a minute, so switching it off stops that address within a minute. Treat a 404 as *no such screen* only when iVendNext's answer names that record; any other 404 (a wrong record type) means iVendNext cannot be read. Count unknown codes per retailer and stop looking them up after a few a minute, so a guesser cannot make you hammer iVendNext, but always look up a code the retailer has made, so guesses cannot lock a real kiosk out. Keep the codes you have seen and the count where every copy of your service reads them: S24 keeps them in each copy's memory, and on CitiXsys hosting it runs as a function whose new copies have seen no kiosk, so a guesser can make a retailer's real kiosks wait (the sample's README, Technical notes).

4. **Ask iVendNext for the price; never work it out yourself.** Two calls with your key, both whitelisted calls of iVendNext:

   ```text
   POST /api/method/ivendnext_mpos.api.v1.scan_barcode                {"search_value": "<scanned text>"}
   POST /api/method/ivendnext_mpos.api.v1.get_item_details {"args": {...one unit...}}
   ```

   The first finds the item from a barcode, a serial number or a batch, with the barcode's own unit. The second finds the price row for one unit on the store's price list, the walk-in customer's own row first, in that unit (a price in the stock unit is converted), on the kiosk's own date. Send `qty` 1, `doctype` `Sales Invoice`, the company, `selling_price_list`, `currency`, `conversion_rate` 1, `transaction_date`, the customer, and `ignore_pricing_rule` 1. ⛔ **Never send a `rate`**: given one, the pricer may write a price row when the retailer's *auto-insert price* setting is on. Show `price_list_rate`; a 0 or no row is *no price here*, never *free*. A 417 from the pricer means iVendNext will not price that item (disabled, past its end of life, a template).

5. **Say what the kiosk does not show.** On iVendNext a selling offer is a **promotion**, which the till works out on the whole sale (the engine refuses a selling price rule), so a one-unit check cannot ask for it. Under every price, say *Any offer is worked out at the till.* The price shown is the store's list price, which a promotion only lowers.

### The kiosk record

What the retailer does after install, in its own words:

- **Before install:** make the role your manifest names, unless it is under your prefix (then the install makes it). The sample's `PP Integration` is made by iVendNext.
- Make your integration user with that role and its API key ([recipe](integration_user.md)), and choose it on your feed registration.
- Make one Kiosk record per screen: where it stands, and the store's till profile. The record's name is the screen's code. Changed the profile's price list later? Save the Kiosk again: its fields are fetched when it is saved.
- On the tablet, open your app's address with `#shop=` and the retailer's site and `&kiosk=` and the record's name, in full screen. A barcode scanner connected to the tablet as a keyboard (USB or Bluetooth) scans into the page.
- To stop a screen, switch its record off or delete it.

## What iVendNext needs from you

- The address of your app, and the words for the tablet's set-up above.
- The note that the kiosk's address works without a sign-in: anyone who has it can check prices at that store, as anyone standing in it can.
- What your service reads from iVendNext (item names, units, public pictures and prices), and that it writes nothing.

## Technical notes

- **Many retailers:** the template's handshake hands your app iVendNext's integration user's key when the retailer connects. iVendNext makes that user after the install, so its key can only travel on a later connect (*Connect again*); until then the kiosk says it is not set up. Name your service's one `*.ivendnext.app` address in the manifest's `allowed_urls`: the site connects only to that address (the POS release that carries the hosted handshake, train T10).
- **Hosting:** a page and a press-only answer, so on CitiXsys hosting it runs as a function, paid per call (`app.json` `"runs": "function"`, [chapter 14b](../guide/14b_deploying_your_app.md)); the sample's `lambda_handler` returns the page with its own content type.
- **Bounds:** a typed item code is not looked up (the sample's 1.0); the price is shown in the till profile's currency, converted by the retailer's own exchange rate when its list is in another (read in the engine's pricer, not run); whoever holds a real kiosk's address can check as often as they like (two calls to iVendNext each); a walk-in customer whose customer group has its own price list is priced on the store's list; online only.

### What was proven where

- **Laptop:** the sample's tests (the core, the service over the wire with one retailer and many, the function entry, the retailer's three calls against a stand-in iVendNext that answers as iVendNext does, the manifest) and its canaries, each RED with its baseline passing.
- **Our test bench:** see the sample's README.
