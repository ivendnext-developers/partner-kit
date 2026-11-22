# What's new for developers

One entry for each iVendNext POS build, newest first: what you can now do, or meet differently, in an app you build. A build that changes nothing you call, check or install says so. The contract pages in this kit are copies taken at the newest build listed here; the [roadmap](roadmap.md) says what we build next.

A build number names the POS app's version: *Build 2.1.0.726* is version 2.1.0.726. An app that needs a feature names the build it first appeared in.

## Build 2.1.0.726 · 22 November

- **A refused install or update lists each refusal on its own line.** When an app's install, update, check, finish or connect-again is refused, the popup shows each refusal with where it is in your manifest (*where (name): reason*, the place in bold), the same list the package's *Refused because* shows. A manifest refused on several rows now shows which row each refusal is about. The server's answers are unchanged.
- **A payment method's discount shows on its button.** A store that sets a discount on a payment method sees it on the method's button on the Pay screen before the cashier picks it.

## Build 2.1.0.724 · 21 November

- **A return of the paid item of a buy-one-get-one.** The till no longer refuses it with *Return both together*; the engine's take-back handles it, shown as *Offer discount taken back*, on an engine that carries the take-back (the engine's development line today; the release customers run never raised the refusal and takes nothing back). A screen that caught that refusal by name meets the take-back instead.
- **An update of a payer app asks before it sends more.** The update lists the new information the payer's service will receive and asks the administrator once, so an app can add a field it sends to its service in an update. A payer service that was switched on keeps running under that agreement.
- **A field rule may name a theme.** A till field rule in your manifest may name a theme the same manifest creates; the theme is installed with the rule and removed with it.
- **A notification is listed under Desk.** The App library lists an app's in-app notification under Desk, not as a connection to an outside service.

## Build 2.1.0.721 · 20 November

- **The install list reads an app's own words.** The record types, the Desk page and the roles of an app read by the words its `translations` give them (the reader's language, else English), as Desk will name them once the app is in; its print layouts and event feeds read by the app's words too, while Desk itself shows those two by their stored names. *Show details* keeps the exact names.
- **A two-for-one's `promo_qty_milli` counts both units**, the paid one and the free one: 2000, not 1000.

## Build 2.1.0.718 · 17 November

Nothing new for developers: no extension page, contract, check or `v1` read changed.

No developer changelog was written for these two releases. What the kit's copies of the product's files hold at build 2.1.0.726 is the reference.

## Build 2.1.0.717 · 17 November

- **An app's install and update lists use Desk's own names** for fields and record types, and a Desk button whose service answers an error says so.
- **Removing an app that brought a receipt layout** empties the POS Profile layouts that named it (receipt, gift receipt, park slip, shift count, shift summary, X-report), so the store prints its own again; the install record's log names each store.
- **An app's report with no page size of its own opens at 2500 rows**, so its *Totals* row adds the whole result. The update gives installed reports the same, unless an administrator saved them by hand.
- **A new or updated app's event feed takes the very next sale**, and a removed app's feed stops at once, with no restart.
- **A partner's coupon check is asked when the coupon is applied**, so a coupon it refuses never shows as applied.
- **The customer display's closing push** names the booked sale's own screen (`mpos_screen`) and its receipt QR beside the engine's answer; a display reading only `screen` keeps the engine's behaviour.

## Build 2.1.0.714 · 16 November

- **An update reads in plain words.** The App library's installer writes each update's lines as *What changes, in plain words*, and a field rule's own words change in an update.
- **An app made from several samples keeps every sample's Desk words** when it is updated.
- **A Desk button whose words change in an update changes in place**, keyed by its record type and service; a second button on the same record type and service is kept.
- **A report's page size comes from your manifest:** 20, 100, 500 or 2500 rows. The checker refuses any other size.
- **The App library opens with every app shown**, and a card shows its version's notes from the library's changelog before and after an update.
- **A payer service's clearing account may be a Bank account**, the type the next platform release requires. Set an existing clearing account's type to Bank before that move.
- **A capture service is asked about an item the cashier picks at the sell screen**, as it is for a scanned item, while the till is online.

## Build 2.1.0.711 · 15 November

Nothing new for developers. It changes how the till settles a phone's points-sale return; no extension point, call or check moves.

## Build 2.1.0.709 · 15 November

- **The print checker's served list is shorter by six record types:** Lead Source, Closing Stock Balance, Homepage Section, Print Heading, SMS Log and Bank Account. The next platform release refuses to serve them to a print, so a partner print that reads one is now warned on today's release instead of passing, and would be refused on the next.
- **A partner key keeps working on the next platform release.** The app's own permission checks for the partner feed, the extension point, partner fulfilment and item availability answer the same on today's release and the next; nothing you call changes.

## Build 2.1.0.706 · 14 November

- **`get_item_details` is answered by the app and takes `args` on every release**, as the kit teaches. It hands the call on to iVendNext's own line pricer, whose checks run as before; its whitelist, guest rule and HTTP methods are unchanged. On the next platform release a call that sends `args` keeps working only through this name.
- **Three pages name Desk at `/app` and at `/desk`:** *Installing a manifest*, *Partner page* and *Station ticket*. A release that serves Desk at `/desk` sends `/app/…` on to it with its query; a call that carries a key should use the address it means and never follow a redirect with the key.
- **One patch clears a stamp on older lines.** Lines a sale or order sent from another store, booked before the previous release, no longer carry the selling store's sale type: you find such a line at the store the goods leave from.

## Build 2.1.0.702 · 13 November

- **The stored *mPOS Receipt* print format is reseeded** where prices include tax: the sale's charges and the delivery fee print under SubTotal and above *Tax (incl.)*, before their tax. Where tax is on top the format is unchanged. A format edited at any of the six reseeded places is left as it is (named in the Error Log), and your own copy of the format is never touched: compare it with the new seed if it should read the same.
- **Five of our fields carry *Print Hide*:** on Delivery Note `custom_mpos_pickup_handed_by` and `custom_mpos_pickup_handed_at`, on POS Closing Entry Detail `custom_mpos_counted`, on POS Opening Entry `custom_origin_channel` and `custom_mpos_drawered_open`. A print format that names one directly still prints it; the standard print no longer does.
- **A planned sale line sent from another store** no longer carries a sale type stamped for the selling store: its fulfilment mode, store and ship-to fields are cleared. A partner reading the board or the fulfilment rows finds the line at the store the goods leave from.
- The receipt change needs the engine's next release: the release customers run today does not carry the method it uses yet.

## Build 2.1.0.701 · 12 November

- **A capture service can be installed beside another switched-on capture service that answers the same event.** The install finishes with the new service switched off and consent recorded, and the package's to-do names the other service and says what to do: give each its own POS Profiles in *Only for these POS Profiles*, then tick *Enabled*. Before, the install stopped with *already answers*.

## Build 2.1.0.700 · 11 November

- **A package can be previewed.** `preview` answers as `check` does and keeps no record on the site; then `check` and install as before.

## Build 2.1.0.699 · 10 November

Nothing new for developers. The release changes the till's own screens and our own checks.

## Build 2.1.0.698 · 10 November

- **A price checker reads a weighed label.** `price_check` reads a price-and-weight label the way the till does: it prices the item the label names for one unit and returns the label's own price and weight beside that price, so a kiosk can show them. A plain barcode answers as before.
- **A payer service's to-do line clears.** The line in *Before each part works* goes away once the service is switched on and has its consent, and comes back if either is undone.
- **A partner capture knows the sale it is scanning into.** On a sale's first scan, `scan_context.sale_ref` carries the reference the sale's first line will take; before, it was empty.

## Build 2.1.0.697 · 10 November

- **Many list prices in one call.** A `v1` read returns many items' list prices at once; an item sold in a pack is priced in its pack.
- **A check sees each line's item name.** Each line in a check's context carries `item_name`.
- **App rights reach a Page and a Report.** An app's manifest can give its role a Page or a Report.
