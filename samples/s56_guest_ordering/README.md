# S56 — Guest ordering (a QR code at the table and a kiosk, to the table's check)

Guests order for themselves. At the table a guest scans the table's QR code, reads the menu on their phone and sends an order: it lands on that table's check on the till, waiting for the server. At a kiosk a counter-service guest orders on a tablet, is shown an order code, and pays at the counter. Staff stay in charge: the app never sends anything to the kitchen and the guest never pays in the app. The page asks no name, phone or e-mail.

![The table card: the table's name, its QR code and Scan to order](screenshots/01_table_card.png)

**Industries:** Hospitality

## Start from it

```bash
ivn new acme_guest --from s56
```

## What to change

What a partner usually changes:

- **The page:** the look and the languages, in `service/page.css` and the `WORDS` table in `service/page.js`.
- **The menu:** allergens from the retailer's own records, in the service's menu read. A dish's picture (its public file on the retailer's site) and its sizes (an Item for each size, named by its template) already reach the page: the page shows the picture or a plain tile, and a dish's sizes together under the dish.
- **The limits:** the course word, and the most lines an order and the most of one dish (no limit of their own unless set), on each row of `PP GOR Store` in `manifest.json`.
- **A new channel:** payment at the kiosk through the retailer's gateway, or a delivery or collection channel.
- **The record types' names:** `GOR_PREFIX` for the service.

Keep the rule that a guest's lines wait unsent: an app given *send to the kitchen* turns a stranger's photo of a table card into food cooked for nobody.

More: the [recipe](../../recipes/guest_ordering.md).

**The customer sets:** the register with **Table Service** ticked, its item groups and price list; the tables as the till's own floor; one `PP GOR Settings` record for the company with a row per store (*Orders from the tables*, *Orders from the kiosk*); the role **PP GOR Manager** for whoever makes the codes; and one *PP GOR Code* for each table and kiosk, made with **Make code** and printed. Nothing for the app's user: the install makes it (the manifest's `app_user_rights`): its own Retail Permission with only *open a check*, *add to a check* and *see the checks*, **Is POS User**, a row for every store (on its Table Service register if it has one), and a Shift Profile.

## Run it

```bash
ivn check
ivn try
```

## Try it at the till

- In Desk, press Make code on a table's code and open its link on a phone.
- Send an order from the phone; it waits on the table's check on the till.
- Close the till day when you are done.

The hosted service reserves 10 of the account's concurrent copies, shared by every store that installs it; a menu read is kept two minutes per copy, so a busy evening's guests read the store once a copy rather than once a guest.

## Versions

### 1.2.3

Manifest 0.2.3. Needs POS build `2.1.0.697` or later.

- The menu's prices are read with the till's `item_prices`: one call for up to 500 items (was one call for each item), so a guest's menu loads faster. A dish the answer leaves out shows no price, a price of 0 shows 0.00 as before, and a busy store leaves the prices to the next read. A till older than build `2.1.0.697` does not know the call: the menu loads with no prices until the retailer updates.

### 1.2.2

Needs POS build 2.1.0.682 or later. Manifest 0.2.2.

- The manifest's `app_user_rights` make the app's own user at the install: its own Retail Permission with only *open a check*, *add to a check* and *see the checks*, **Is POS User**, a row for every store (on its Table Service register if it has one), and a Shift Profile, so the administrator sets nothing up by hand (a user already set up by hand stays as it is).

### 1.2.1

Manifest 0.2.1.

- *Make code* on several records says *Print each card from its form's Print menu*, not *Print its card*.
- `role_rights` give **PP GOR Manager** *Read* and *Select* on *Retail Floor Place* and *Select* on *Warehouse*, so the people who make the codes need no Role Permissions step.

### 1.2.0

- The guest page reads like a menu: each dish has its picture (a plain tile where it has none), a dish sold in sizes shows once with its sizes together, prices carry the store's plain currency sign, and a running total sits beside *Send order* while the order stays in view.
- A menu priced more slowly than the read allows no longer stays blank: the service reads prices in as few calls as it can (1.2.3: one call for up to 500 items) and keeps a late menu only 2 seconds, and the page asks again after 3 seconds, up to three times, taking the prices into the menu the guest holds. A store that answers *busy* or slowly gets those prices asked at the next read.
- A dish the till refuses at the add (sold out, or not sold now) is said to the guest in the till's own words, naming the dish (*Not available now: Latte (sold out). Take it off to carry on.*).
- Sizes show cheapest first and the cheapest is picked; a size's line on the order reads *Dish · Size*; an answer to *Send order* is scrolled into view above the sticky panel.
- The retailer's words sit in `<bdi>` inside a block of the page's own direction, never a guessed one (as S59).
- A link whose number is written in non-ASCII digits no longer works.

### 1.1.0

- The role's rights beyond the feed's reads move into the manifest (`role_rights`): the install gives the feed's user its reads and the manifest the rest, so the retailer's administrator grants none. Needs POS build `2.1.0.691` or later.

### 1.0.1

- Two guests at a free table land on one check with no wait; the limits on an order are blank unless the store sets them; a dish sold out since the menu says so.

### 1.0.0

- First version in the kit: a QR code at the table and a self-order kiosk, to the table's check.
- Each setting in app.json says its purpose (the line the Settings screen shows), whether it is required, and which settings go with it.
