# S17 — an order board (`pp_pge`): a partner page

![The order board on the till, end to end](screenshots/s17_flow.gif)

*A cashier presses **Deliveries** on a sale, the partner's board opens over the sale in the till's own look, and after *Attach to sale* the delivery number is on the sale.*

Your own screen, shown inside iVendNext: on the till as a sheet over the sale, and in Desk as a page for a record. This sample is for a developer whose service has a screen of its own (here, a delivery board) and who wants cashiers and staff to use it without leaving iVendNext POS.

**When to use it:** your service needs its own screen in the till or in Desk, and may hand one answer back to the sale.

## What happens

On the till (counter and tablet):

1. The cashier presses the **Deliveries** key on a sale.
2. The board opens as a sheet over the sale. It offers a delivery order number.
3. The cashier presses *Attach to sale*.
4. The board's **server** answers the till once. The till shows its usual confirm sheet, with the sale detail *PP PGE Delivery Order*.

In Desk, the same board opens as a page for a record (`/app/partner-page/<page>?doctype=Sales Order&name=…`), for Stock Users and Stock Managers.

iVendNext opens the page with a **signed, one-time context** in the address's fragment (`#ctx=…`): who is looking, at what, for five minutes, once. The board checks it on its own server, and never holds the retailer's session.

## What it looks like

The names in the pictures are a demo site's: a cashier selling to a customer on the till, and a stock user opening the board for a Sales Order in Desk (step 5).

| Step | Frame | Screenshot |
|---|---|---|
| 1. A sale with one item; the **Deliveries** key sits with the till's other keys | the till, `/pos?frame=terminal`, 1440 wide | ![](screenshots/01_till_deliveries_key.png) |
| 2. The board, framed as a sheet over the sale, drawn with the till's own tokens | the till, 1440 wide | ![](screenshots/02_board_on_till.png) |
| 3. After *Attach to sale*: the till's own confirm sheet, with the sale detail and the number | the till, 1440 wide | ![](screenshots/03_till_confirm_sheet.png) |
| 4. Applied: the delivery number is on the sale (*Sale details*) | the till, 1440 wide | ![](screenshots/04_sale_detail_on_sale.png) |
| 5. The same board in Desk, as a page for a Sales Order | Desk, 1440 wide | ![](screenshots/05_board_as_desk_page.png) |

The sale detail reads *PP PGE Delivery Order* because our samples carry the placeholder prefix `PP`; a partner's copy shows its own name, under its company's first word.

## What the retailer does

**Before you install:** every `host.docker.internal` address in `manifest.json` (in `allowed_urls`, and where the manifest calls it) is our test bench's own address for the sample's service, and it resolves only where Docker provides it. Replace it with your own service's address first, or iVendNext's calls never reach your service; if this manifest is already installed, raise its `version` and install it again ([the manifest recipe](../../recipes/manifest.md), step 6).

1. **Install the app.** It comes in switched off, and adds one sale detail, `PP PGE Delivery Order`, which the board answers with. The app names no role of its own.
2. **Read what the page will receive.** Open **Retail Extension Subscription**, the record *Deliveries*. The consent text is built from what the page asks for: here the sale as the till holds it (that includes the cashier's login and the customer's id) and not the viewer's login.
3. **Tick the consent and switch the page on.** If the page's address ever changes, the consent is cleared and the till's key says why it cannot open; switching the page off and on again does not bring the consent back, only ticking it does.
4. **Place the Deliveries key on the till.** In **POS Studio > Apps**, place the key for the till theme.
5. **Nothing more to set for Desk.** The page is given to a Stock User or a Stock Manager who may also read that record; anyone else is told *"You can't open this page for that record."*

**Where it shows.** On the counter and tablet till, the **Deliveries** key opens the partner's board as a sheet over the sale, in the till's own look; after *Attach to sale* the delivery number is on the sale as the sale detail `PP PGE Delivery Order`. In Desk the same board opens as a page for a record (a Sales Order here). The phone shows no app keys, so no page either, and the key is dimmed when the till is offline. Nothing is added to a print layout or a report.

**What leaves the retailer's iVendNext.** One address: the partner's board (the manifest ships a test address; the partner writes its own, on its own host: iVendNext refuses an address on its own site). Each time the page opens, iVendNext hands it a signed, one-time note (its context), good for five minutes: on the till, the store, the POS Profile and the sale as the till holds it (no money), the cashier's login and the customer's id included; in Desk, the record's type and name; and the till's colours and type size so the board can look like the till. The viewer's login is not sent. What comes back is one answer from the partner's server to iVendNext: a message and the delivery order number. The page holds no key of its own for the retailer's iVendNext. There is no webhook, no event feed and no remote till key.

## The files

| File | What |
|---|---|
| `manifest.json` | the page (`extension_subscriptions`, extension point `page`, *Till key and Desk page*) and the sale detail it answers with, installed **switched off** |
| `page.py` | **the pure core**: read and check the context (signature, expiry), the nonce-once set, the till's answer and its signature |
| `service/app.py` | the HTTP service (standard library): `GET /board/`, `POST /board/api/open`, `POST /board/api/answer` |
| `service/board.html` | the page: reads the fragment once and takes it out of the address, never puts context text into markup, and draws with the retailer's design tokens the way the till's own sheets do (the till's type, a bold title, muted detail rows, one full-width button) |
| `tests/test_service.py` | laptop tests: the real service, contexts minted as iVendNext mints them, a stand-in for the retailer's `api/page.submit` |
| `tests/test_contract.py` | the answers, and every context our test site minted, against the published contract (`partner_page.v1.schema.json`) |

The recipe is `recipes/partner_page.md`.

## How to run it

Start the service on your server, under your own process manager: `python3 service/app.py service/.env.local`. Install the manifest in the retailer's iVendNext. It installs switched off: the retailer reads what the page will receive, ticks the consent, switches the page on, and places the **Deliveries** key on the till (the recipe has the steps).

To start the service, run this with its settings in `service/.env.local`:

```bash
cd samples/s17_partner_page
python3 service/app.py service/.env.local
```

## What is refused, and why

- **A second answer for one context.** The board refuses it itself, and iVendNext refuses it again (*"This page has already answered."*). Either lock is enough on its own: the till takes the first answer only.
- **A page on the retailer's own address.** iVendNext refuses it: write a page address on your own host.

## When iVendNext cannot be reached

If iVendNext cannot be reached when the board answers, the board says so and the cashier presses again. The context's one answer is not used up.

## Before you copy it

- **Where it has been checked.** On the counter till only, in light mode, at the default text size. Where the till's font is not installed, the board draws in the system font, as the till does.
- **Remember opened contexts in your database.** This sample keeps them in memory, so a restart forgets them: a context opened just before a restart could be opened once more within its five minutes.
- **What the till takes back.** A page can answer with a message and sale details. Details on single lines are not supported yet.
- **What the till sends.** The sale includes the cashier's login and the customer's id. The board shows only the line count and the store. If you do not need the sale, switch sending it off (`page_send_sale`). The viewer's login is not sent (`page_send_user`).
- **Test routes.** Delete `/test/once` and `/test/opened` from your copy.
- **Your address.** Write your own page address in `allowed_urls`.

## Technical notes

### What was walked, and where

The GIF: frame: the till, `/pos?frame=terminal` in a 1440-wide window. Walked on our test bench on 2026-10-10, iVendNext POS app at `87812e141`. Built from the same screens as the stills, uncropped.

The stills: walked in a real browser on our test bench, 2026-10-10, iVendNext POS app at `87812e141`. The board names the store's warehouse as the kit's demo site has it (*Demo Retail — Store 1 - DR*). On the till, the bench's demo cashier (*Thabo Nkosi*) sells to *Naledi Khumalo*; in Desk (step 5), a stock user (*Nomsa Zulu*) opens the board for a Sales Order.

On our test bench the page was opened through the till's own press and pick-up and Desk's own context call, for every case in the recipe. `tests/test_contract.py` checks every context the bench minted.

### Why it is built this way

| Option | Cost | Verdict |
|---|---|---|
| Do nothing | 0 | row 48 (the delivery partner's screen on the till) has no sample to copy |
| A static page that only shows the context | ~40 lines | skips the two duties that matter: checking the context on the server, and answering once |
| **A pure core + a standard-library service + one HTML page** | ~300 lines | **picked**: every duty P-PAGE gives the partner, in code a new developer reads unaided |

**Two locks on one answer.** The board refuses a second answer for one context itself, and iVendNext refuses it again (*"This page has already answered."*). Either is enough; the bench proves both.

### Bounds, stated

- **Walked** on 2026-10-07 and again on 2026-10-10 on the till's counter frame, light mode, text size 1 only. The board names the till's font (IBM Plex Sans) but cannot load the till's font file: where it is not installed, the board draws in the system font, as the till does.
- **The viewer's login is not asked for** (`page_send_user` 0): the board does not need it, so iVendNext is not asked to send it.
- **If iVendNext cannot be reached** when the board answers, the board says so and the cashier presses again; the context's one answer is not used up.
- **The nonce sets are in memory.** A restart forgets them, so a context opened just before a restart could be opened once more within its five minutes. A partner keeps them in its own database.
- **The till's answer kinds.** At the bench's pin the till takes `message` and `sale_attributes` from a page. The spec's `line_attributes` (P-CAPTURE) is not there yet.
- **A message from another origin** (S4) and the frame's attributes are the till's own tests (Jest, in the POS app): not re-run here.
- **The contract test** reads the extension points' contract files in [`contracts/`](../../contracts/README.md), which ship in this repository.
- **The sale the till sends** (`page_send_sale` 1) includes the cashier's login and the customer's id: the board shows only the line count and the store. A partner that does not use the sale sets it to 0.
- **Test routes.** `/test/once` and `/test/opened` exist only with `PP_TEST_MODES=1` and the admin token. A partner's copy deletes them.
- **`allowed_urls`** names our test bench's HTTPS front. A partner writes its own page address, on its own host: iVendNext refuses a page on the retailer's own address.
