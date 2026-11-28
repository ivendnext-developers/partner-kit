# Production station: price and tag donated goods at a station, count by worker, send carts to stores — the recipe

A thrift chain's processing room sorts donated goods, prices each piece from a short list of price points, tags it and puts it on a cart for a store. The tag carries the price inside its barcode, so the till charges it; its colour says which week it was made, so a store can mark down a colour that has stayed too long. This recipe gives each station a screen a worker learns in one shift: their name once, then a category and a price, one tag a tap. *Cart full* puts the cart into stock at no value and moves it to the store. A Desk report counts who tagged how much, by day and hour, and what each colour week sold.

**Reference implementation:** `samples/s64_production_station/`.

**When to use it.** A processing room that tags from fixed price points by category, with a tag colour that turns each week: a charity's thrift stores, a resale chain's sorting centre. The workers need no iVendNext user and no sign-in.

**The four rules, here.** No code runs inside the retailer's iVendNext. One address is called, your service: by the two Desk buttons and by each station's page. The service reads and writes as the app's own user, through the record API, the engine's own label encoder and barcode reader, the till's partner API (`get_count`, `bulk_update`, `run_report`) and nothing else. It moves no money and states no value: the stock is received at no value, and the price is in the tag.

## Steps

<a id="settings"></a>
### Settings

1. Install the manifest, and give the production lead the role **PP PST Manager** first (the install makes it with no user, with *Select* on Company, Warehouse and Item Group): the lead makes the settings and the stations. The manifest adds the settings (one per company), the station record, the tag, the cart and the production report record types, two fields (*Tag colour*, one small field on Item; *Production cart* on Stock Entry), four reports, the roles **PP PST Manager** and **PP PST Integration**, the buttons *Make link* and *Work out* and their services, and the feed registration that makes the app's own user. The manifest's `role_rights` give the app's role read on Item, Warehouse and System Settings (the site's time zone: today's colour is the site's own date), read, write, create and submit on Stock Entry, the lookups those need, and, for sell-through, the retailer's own *POS Sale Report* with Read and Report on POS Invoice (the till's sales). It reads no customer and sends nothing elsewhere.
2. **The items.** One item per category and colour: an item group per category (*Women's tops*), and in it an item for each tag colour, its **Tag colour** filled (*Blue*). Each is on the site's price-in-barcode **Barcode Mask** (the item barcode, the price in cents, the factor 100) with a barcode of its own. The station finds the item for the category and today's colour, so a worker never picks a colour.
3. **PP PST Settings** for the company: the **processing room** (a warehouse); the tag's **width** and **height** in millimetres (50 by 30 unless changed); the **colours** in rotation order and **First colour week starts** (the colours turn every seven days from that day, and start again; **Colour for one day** and **On** override one day); the **workers**' names (untick *Active* when one leaves: their tags stay counted); the **price points** of each category (the only prices a tag carries); and the **places a cart can go**, each a warehouse (a store, the outlet, salvage, the online department; the processing room itself keeps a cart there).

<a id="stations"></a>
### Stations

4. The lead (**PP PST Manager**, which the install makes with no user, or a System Manager) makes a **PP PST Station** for each station and presses **Make link**: the station's number goes up by one and its signed link is written on it. A station open with an earlier link stops within 15 seconds.
5. **The station's browser.** In the shortcut that opens the browser on the station, add `--kiosk-printing` after the program's name in the shortcut's *Target* box (`"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk-printing`; the same after `msedge.exe` for Edge), make the label printer the default printer, and open the link with that shortcut. Each tap then prints with no window. A tablet opens its print sheet on each tag: one more tap.
6. **The label printer.** The tag is sized in millimetres from the settings, and the page prints it on a page of that size with no margin: set the same width and height in the printer's driver, and print one tag on your own printer and tag stock before the first shift.

<a id="tags"></a>
### Tags

7. The worker taps their name (kept on the station's browser until **Change worker**), a category and a price. The service checks the worker, the category and that the price is one of the category's price points, finds today's colour and the category's item of that colour, and has the engine make the barcode with the price inside (`get_item_barcode_for_label`). **The first time a price is printed, the engine reads the barcode back** (`resolve_barcode`): the tag prints only when it reads as the same item at the same price, which is what the till will charge. Then one **PP PST Tag** is written (station, worker, category, item, colour and the colour week's first day, price, barcode, day and hour) and the page prints it: the price large, the category and the colour, the Code 128 barcode drawn by the page itself, and its digits.
8. **Undo last tag** takes back the last tag printed at this station, before its cart is sent. A tag taken back is never received. A tap or an undo whose answer did not come back is tapped again: the same tap counts once.

<a id="carts"></a>
### Carts

9. **Cart full** shows the places; a tap sends the cart. The service gathers the station's tags since the last cart, makes a **PP PST Cart** and posts, as the app's own user, a **Material Receipt** of the tags into the processing room, one line per item at rate 0 with *Allow Zero Valuation Rate*, then a **Material Transfer** of the same lines to the place chosen. Both name the cart in *Production cart*. A cart kept in the processing room gets the receipt only, and moves later with the engine's own transfer or on the Handheld.
10. **Each cart posts once.** Before each entry the service looks for a submitted one that names the cart and takes it instead. A second tap of a cart just sent answers the same cart; a tap after a lost answer, or after a failure between the two entries, continues the same cart and finishes it (within a minute of the first it says the cart is being sent). A place that cannot take the cart says so, and another place tapped sends the same cart there; its receipt is never posted again. A station has one open cart at a time, and a cart kept in the processing room stays where it was received whatever the settings later say.
11. The lead may type the cart's **Pounds** in Desk. After a cart is sent, a correction is the lead's own stock entry.

<a id="reports"></a>
### Reports

12. The lead makes a **PP PST Report**, names two dates (and the settings, if the site has more than one company's) and presses **Work out**. It writes a row per day, station and worker (pieces, the clock hours in which the worker tagged, pieces per active hour) and a row per colour week that overlaps the dates: *tagged* (the week's non-void pieces), *sold* (that colour's units in the retailer's own *POS Sale Report* at the places that are stores, from the week's first day until the colour's next turn, or today) and *sell-through* (sold ÷ tagged; blank when nothing was tagged). Each press replaces the rows.
13. Four reports list them: **Production by worker**, **Sell-through by colour**, **Carts** and **Tags** (every tag; Desk groups them by category, hour or price).

## Limits

- A price that is not one of a category's price points is never printed at the station: one-off pieces are priced in the store.
- A site whose labels do not carry the price their scan reads back (an engine before its label fix of 12 October 2026) refuses the prices it cannot carry, with *This price cannot be printed on a tag yet. Tell your lead: iVendNext needs an update.*
- A cart holds at most 5,000 tags; a report covers at most 92 days.
- *Sold* counts every unit of the colour's items at the stores in the window, the colour's earlier weeks' pieces too.
- A station needs the internet: no tag prints offline.

## Technical notes

- **The link is an authorisation.** A station's link carries the site, the station record, its number and an HMAC-SHA256 signature of the three with the *Make link* subscription's secret, after `#`. The service checks the signature before it reads anything, then reads the record and refuses a link whose number moved on or whose station moved to other settings. The number, the link and what it was made for are written only by the app's role and System Manager.
- **The page decides nothing.** The price, the colour, the item and the barcode are the service's answer; the page prints exactly that. Its policy allows nothing from another site, no inline script and no image.
- **A cart posted once.** Each stock entry is made submitted in one call. Before it, the service looks for a submitted entry of the same purpose naming the cart. A cart written in the last minute is being posted by another call, so a second call answers *busy*; the cart's hidden *Open for* field is unique, so two calls at once make one cart.
- **Today's colour** is the site's own date, from its time zone (System Settings), read once an hour. A copy of the function keeps a verified station and its settings for 15 seconds, a category's item of a colour for a minute, and a price the engine read back for ten minutes: the next tag at that price is one write.
- **Counting.** *Work out* reads the tags with one grouped read (the record API's `group_by` with `sum(quantity)`) and, where a site refuses that, a page of rows at a time. The press has 7 seconds.
