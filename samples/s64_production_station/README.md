# S64 — Production station (`pp_pst`): price and tag donated goods at a station, count by worker, send carts to stores

A thrift chain's processing room sorts and prices donated goods all day. At a station's screen a worker taps their name once, then a category and a price point: one tag prints, with the price inside its barcode, in this week's colour. The category stays chosen, so the next piece of the same kind is one tap. **Cart full** puts the cart's pieces into stock at no value in the processing room and moves them to the store, the outlet or wherever the cart goes, in one tap. The production lead reads who tagged how much, by station, day and hour; the head of retail reads sell-through by tag colour.

**Industries:** Thrift and resale

**When to use it:** a processing room tags priced goods from fixed price points by category, with a tag colour that turns each week, and its workers are not iVendNext users (many are in job-training programmes: the screen is learned in one shift).

## Start from it

```bash
ivn new acme_production --from s64
```

## What to change

What a partner usually changes:

- **The tag:** its layout in `service/page.css` (the print-only part) and `printTag` in `service/page.js`; its width and height come from the settings. A condition or grade on each piece, or a second line of text, is a partner's version.
- **The words and languages:** the `WORDS` table in `service/page.js` (English and Spanish here).
- **Printing:** the page uses the browser's own print. For raw printer commands through an agent on each station (a tag in well under a second on a label printer's own language), replace `printTag` with a call to that agent.
- **The report:** what *Work out* counts, in `pst.py` (`worker_rows`, `colour_rows`) and `Service.work` in `service/app.py`.
- **The names:** the record types in `manifest.json`; `PST_PREFIX` names them for the service.

More: the [recipe](../../recipes/production_station.md).

**The customer sets, in this order:**

1. **Tag colour** on each category item: one item per category and colour (an item group *Women's tops* with an item for Blue, Green, Pink …), each on the site's price-in-barcode mask (*Barcode Mask* on the item) with its own barcode.
2. **PP PST Settings**, one for the company: the processing room; the tag's width and height (50 by 30 mm unless changed); the colours in rotation order and the day the first one starts (*Colour for one day* and *On* when the lead needs to override one day); the workers' names; the price points of each category; the places a cart can go (each a warehouse; the stores among them are counted for sell-through when they are marked *Is Retail Store*).
3. A **PP PST Station** for each station, with **Make link** pressed and the link opened on the station's browser.
4. **The station's browser.** Chrome or Edge opened with its print-without-asking switch, `--kiosk-printing`, and the label printer as its default printer: each tap then prints with no window. On a tablet the system's print sheet opens on each tag: one more tap.
5. The role **PP PST Manager** for the production lead (the install makes it with no user; a System Manager can do everything it does). It keeps the settings, the stations, the carts' *Pounds* and the production reports.

The manifest's `role_rights` give the app's own role what its service needs and no more: read on Item, Warehouse and System Settings (the site's time zone, for today's colour), read, write, create and submit on Stock Entry (the carts' two entries), the lookups those need, and *POS Sale Report* (sold units for sell-through) with its lookups.

**The engine it needs.** A site whose price labels carry the price their scan reads back: the engine's label fix of 12 October 2026. The app checks every price before it prints it the first time: the engine reads back the barcode it made, and the tag prints only when it reads as the same item at the same price. On an older site a price it cannot carry is refused with *This price cannot be printed on a tag yet. Tell your lead: iVendNext needs an update.*, and prices it can carry still print.

## Run it

```bash
ivn check
ivn try
```

The tests: `python3 -m unittest discover -s samples/s64_production_station/tests -p 'test_*.py'` (97 laptop tests) and `python3 samples/s64_production_station/tests/canaries.py` (each check that can fail, removed one at a time).

## Try it at the till

- In Desk, press Make link on a station and open the link in a browser.
- Tap a worker, a category and a price: a tag prints. Tap Cart full and choose a store.
- Scan the tag at the till: it rings at the tag's price. Close the till day when you are done.

## What it does not do

- It moves no money and states no value: the stock is received at no value, and the price is in the tag.
- After a cart is sent, a correction is the lead's own stock entry in Desk.
- A price at the station is always one of the settings' price points: one-off pieces are priced in the store.

## Versions

### 0.1.0

- First version in the kit: the station's screen and its tags, the colour of the week, Cart full posting each cart once, and the production report by worker and by colour week.
