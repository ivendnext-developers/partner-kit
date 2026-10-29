# Guest ordering: a QR code at the table and a self-order kiosk — the recipe

Guests in quick service and full service expect to order from their phone at the table, or from a kiosk at the counter. The till already keeps a table's running order (the open check), the register's menu (its item groups, price list and the dishes' choices) and the floor's tables; what it does not have is a door for the guest. This recipe gives each table a printed QR code and each kiosk a link: the guest reads the register's own menu on their phone and sends an order, which lands as lines on that table's check through the till's open-check door, unsent, for the server to read and send to the kitchen. A kiosk order opens a tab named by an order code, paid at the counter.

**Reference implementation:** `samples/s56_guest_ordering/`.

**When to use it.** A store with *Table Service* on its register: full service, a café or bar with table ordering, a hotel's restaurant; a quick-service counter with a kiosk. The tables are the till's own floor (*Retail Floor Section* and *Retail Floor Place*); the menu is the register's item groups and price list; a dish's choices are its *Retail Option Groups*. Payment in the app, delivery and collection come on top (*Make it your own*, below).

**The four rules, here.** No code runs inside the retailer's iVendNext. One address is called, your service: by the *Make code* button, and by the guest's phone. The service writes to a check only through the till's door (`check_open`, `check_add_lines`), as the app's own user, with the three rights guest ordering asks for: *open a check*, *add to a check* and *see the checks*. ⛔ Never *send to the kitchen*: a guest's lines wait for a person. The page asks no name, phone or e-mail.


## Steps

### Settings

1. Install the manifest. It adds the settings (one per company, with a row per store), the code record, the print format *Table card*, the roles **PP GOR Manager** and **PP GOR Integration**, the button *Make code* and its service (off), and the feed registration that makes the app's own user (`pp_gor@integration.invalid`; leave the feed off).
2. Give the app's user its store and its key, in this order, on its User record: keep *Is Desk User*, tick **Is POS User**, choose a **Shift Profile**, link a **Retail Permission** with *Open Checks*: **open a check**, **add to a check** and **see the checks** only; add one row for each store to the store access table (each store once, with its register there, *Table Service* on); **Save**; then **Generate Keys**. Without *Is POS User* the save drops the store row and the till answers *"You are not assigned to this outlet."* Never give it write on *Floor Section*: that is every check verb, a comp included.
3. In **Role Permissions Manager**, give **PP GOR Integration** **Read** on *Item*, *POS Profile* and *Retail Option Group*; give **PP GOR Manager** to the people who make the codes, with **Read** and **Select** on *Retail Floor Place* and **Select** on *Warehouse*.
4. On **PP GOR Settings**, one row per store: **the same register** the app's user holds there (its **Item Groups** are the menu: list each group, a group's sub-groups are not read), *Orders from the tables*, *Orders from the kiosk*, the course word (*Guest order* to start), the most lines one order holds and the most of one dish (10 and 10 to start). Consent to the service and switch the button on; press **Connect again** on the app's package record if the site could not reach the app.

### Codes

5. The manager makes a **PP GOR Code** for each table (kind *Table*, the store, the table) and for each kiosk (kind *Kiosk*, the store, a name) and presses **Make code** (on one record, or on many ticked in the list). The service writes the code's number, its link and its QR picture; **Print**, *Table card*, prints the table's name, the QR code and *Scan to order*.
6. A code that leaked is replaced by pressing **Make code** again on that record: its number goes up by one and the old card stops working (within 15 seconds). Changing a code's kind, store, table or kiosk name stops it working until *Make code* is pressed again, so a card never orders for another table.

### An order at the table

7. The guest scans the card: the page shows the register's menu, each dish with its price (*prices before any offer*), *Choose* for a dish's choice groups, a note for the kitchen on each line, and **Send order**.
8. The service checks the order against the menu and the store's limits (a dish on the menu, a whole quantity up to the store's most, each choice the dish's own, each group's least and most picks), then, one order a table at a time (whichever of the table's cards it came from): **no check open** at the table, it opens one and adds the lines; **one open**, it adds the lines to it, unless a till is taking its payment (*please ask your server*: lines added then would keep the check open after the party leaves); **more than one**, it refuses (*please ask your server to take your order*).
9. The lines wait unsent under the course word. When the server's own lines wait too, the till's **Send** asks which course to send; when only the guest's wait, **Send** sends them as usual, so the server reads the check first. The table pays at a till as any check.

### An order at the kiosk

10. The kiosk's tablet opens the kiosk's link in a full-screen kiosk browser, so its address is not on show. The guest orders the same way; the service opens a **tab** named *Kiosk* and a five-character code (letters and digits that cannot be misread), adds the lines, and shows *Your order is 7KQ2M. Please pay at the counter.* The counter finds the tab on the till's floor under *Tabs* and pays it; the receipt's call number calls the order. The counter's register that takes the payment has *Table Service* ticked too (a tab is claimed only there) and rings the app's register's service mode.

## What the retailer does

Day to day the guests order and the servers work the checks at the till as before. The app never sends to the kitchen, prices, moves, merges, closes, voids, comps or prints a check, and never takes a payment: those are a person's decisions, at a till.

## Limits

- One order per table (or kiosk) every 15 seconds: a family's second phone waits a moment.
- A kiosk link copied from the tablet lets anyone open unpaid tabs, one every 15 seconds, until *Make code* is pressed again.
- A check the app opened can be left empty (a dish refused at the add at a free table, or a retry after the bill was paid); the server closes it. A till opening a check at the same moment as a guest's first order can leave two checks at the table.
- A guest's note for the kitchen is kept on the check line like any note.
- A guest at a place one party already holds (a bar counter, a shared table) joins that party's bill: one place per party, or phone orders off for shared places.
- A card works whenever its store takes orders, after closing too: switch *Orders from the tables* off at closing.
- A kiosk tab a guest walks away from stays open: a cashier with *change any line* and *close an empty check* removes its lines and closes it.
- A table with more than one bill open takes no guest order until the server merges or pays one.
- A guest's lines show on the till under their course and note, not as the guest's: when they are the only lines waiting, *Send* sends them with no question.
- The menu is the register's listed item groups (no sub-groups), at most 300 dishes; dish names are the retailer's own words as written. No pictures, allergens or *sold out*.
- A check the app opens has no party size; the server sets it at the till.
- A reinstall makes new secrets: every code is made and printed again. A new secret on the *Make code service* is accepted beside the old one until the next *Connect again*; to stop one card, press *Make code* on it.
- A dish with no price on the register's price list shows 0.00.
- Ordering needs a connection: nothing here works offline.

## Technical notes

- **The code is an authorisation.** A code's link carries the site, the code record, its number and an HMAC-SHA256 signature of the three with the *Make code* subscription's secret (`#s=…&t=<record>.<number>.<signature>`, after `#`, so it never reaches a server log or another site's referrer). The service checks the signature before it reads anything, then reads the record and refuses a code whose number moved on or whose kind, store, table or kiosk name no longer matches what it was made for. The store, the table and the register come from the record and the store's row, never from the page. *Connect again* resends the same secret, so printed codes survive it.
- **What makes a code work is the app's.** The number, the link, the picture and what the code was made for carry `write_roles` of the app's role and System Manager: a manager cannot lower a number to bring a leaked code back.
- **One order a table at a time.** Before it reads the floor the service takes a claim on the table (its store and place; a kiosk's record) in its own table (`shops.claim`, a conditional write every copy of the function sees), held 15 seconds: two guests at a free table never open two checks, from one card or two, and a flood of orders is spaced. A check whose lines a till is paying (`status` *paying* on the floor) takes no guest order.
- **One read a code.** A copy of the function keeps a verified code and its store's row for 15 seconds and a store's menu for two minutes (ten seconds when a price came back late), so calls on one code read the retailer once per copy in that time.
- **One order, never two.** The page makes one random key per *Send order* and sends it again on a retry; the service makes the door's two keys from it (`door_key`: a hash of the page's key and the step, `open` or `add`), so a retry returns the door's first answers and writes nothing twice. A retry whose first send landed on a check since paid or moved is refused by the door (`CheckRequestError`), and the guest is told the order was already sent once.
- **No price leaves the service.** A line carries the dish, the quantity, its choices (`{item_code, option_group}`), the guest's note (one line, 80 characters) and the course; never a price or a discount. The menu's prices are read from the retailer's own line pricer (`get_item_details`, never a rate) and shown only to the guest.
- **The page.** `page.html`, `page.js` and `page.css`, served by the service with a policy that allows its own script and style only (no inline script, nothing from another site, no referrer); every word the retailer wrote is set as text, never markup, with `dir="auto"`.
- **The kiosk's code** is five characters from 31 letters and digits, an HMAC of the page's key with the retailer's secret: the same on a retry, never chosen by a guest.
- **The QR picture** is drawn by the service (`qr.py`: byte mode, level M, versions 1 to 10), written on the record as a `data:` SVG address, and printed by the print format with one whole `{{ doc.qr }}` reference: a print format may load nothing from outside the retailer's iVendNext. The card prints the code only when its link names that very record and number and the record still matches what it was made for, so a record duplicated in Desk prints *Press Make code first*.

## Make it your own

A partner usually adds the page's own look and languages, pictures and allergens from the retailer's records, payment at the kiosk or at the table through the retailer's gateway, and delivery or collection. Start with `python3 tools/manifest/start.py s56_guest_ordering --prefix "ACME GOR"`.
