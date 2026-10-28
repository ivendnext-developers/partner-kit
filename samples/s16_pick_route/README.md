# S16 — *Assign pick route* (`pp_pck`): a Desk action

*Start from this sample: `python3 tools/manifest/start.py s16_pick_route --prefix "ACME PCK"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

![Assign pick route, end to end in Desk](screenshots/s16_flow.gif)

*A stock user presses **Warehouse → Assign pick route** on a Sales Order, picks a colleague and a priority, and the partner's service opens a pick task listed under the order.*

A button in iVendNext Desk that hands a record to your own service, which does real work and answers. This sample is for a developer who wants a press in Desk to create something in their system: here, a pick task for a Sales Order.

**When to use it:** you want a button on a Desk record that sends the record to your service and shows the answer.

## What happens

1. A stock user opens a submitted Sales Order and presses **Assign pick route** (menu *Warehouse*).
2. iVendNext's own dialog asks for a picker and a priority. The user fills them in and confirms.
3. iVendNext sends the order's lines to your service, signed.
4. Your service creates a **pick task** (`PP PCK Pick Task`, this app's own record type) over the record API, **with its own key**, then answers.
5. The task opens. It is also listed under the order (Connections, *Picking*).

The Sales Order itself does not change. From the order list, the same button runs on several orders at once (one task each, one message), up to 20 in one press.

## What it looks like

The names in the pictures are a demo site's: a stock user, a customer's order, and a colleague picked as the picker.

| Step | Screenshot |
|---|---|
| 1. A submitted Sales Order: the **Warehouse** menu holds *Assign pick route* | ![](screenshots/01_warehouse_menu.png) |
| 2. iVendNext's own dialog: *Picker* and *Priority*, filled in | ![](screenshots/02_dialog_filled.png) |
| 3. The partner's answer: *Route assigned — 2 lines across 2 warehouses* | ![](screenshots/03_route_assigned.png) |
| 4. The pick task the service made, opened: the order, the picker, the priority, the lines in walking order | ![](screenshots/04_pick_task.png) |
| 5. The order's **Connections**: the task is listed under *Picking* | ![](screenshots/05_order_connections.png) |

## What the retailer does

**Before you install:** every `host.docker.internal` address in `manifest.json` (in `allowed_urls`, and where the manifest calls it) is our test bench's own address for the sample's service, and it resolves only where Docker provides it. Replace it with your own service's address first, or iVendNext's calls never reach your service; if this manifest is already installed, raise its `version` and install it again ([the manifest recipe](../../recipes/manifest.md), step 6).

1. **Install the app** (the retailer's administrator). It comes in switched off: the service has no consent and is off, and the button is off. The install adds the pick task record, `PP PCK Pick Task`, and the role **PP PCK Integration**, with no one in it.
2. **Hand the service its key** (the retailer's administrator). From POS 2.1.0.667 the install made the app's own user, `pp_pck@integration.invalid`, and named it on the feed **PP PCK Pick feed**. It holds the role **PP PCK Integration** alone, works through the API only and can never sign in to Desk, so there is no user to make and no role to give. With its key the service can read and create pick tasks and nothing else. A service for many retailers is handed the key by the retailer's site itself, after the install or an update (*Many retailers, hosted* below); press **Connect again** on the app in the App library only if the site could not reach the app, or a key was lost or changed. A service for one retailer: press *Generate Keys* on that user (User, API Access) and put the key in the service's settings.
3. **Switch the service on** (the System Manager). Open **Retail Extension Subscription**, the record *Pick route service*, read what it is sent, tick the consent and switch it on. A change to its address or to the list of fields clears the consent until it is ticked again.
4. **Switch the button on** (the System Manager). Open **Retail Desk Action**, the record *Assign pick route*, and switch it on.
5. **Stock users press it.** Only a Stock User or a Stock Manager sees the button, and only on a submitted order that is *To Deliver and Bill* or *To Deliver*. They choose a picker (a colleague) and a priority (*Normal* or *Urgent*) in iVendNext's own dialog. Stock Managers and Stock Users can open and update a pick task but not make one by hand; the System Manager can do everything with it.

**Where it shows.** In Desk only. The button sits in the **Warehouse** menu of a submitted Sales Order, and in the order list's Actions menu for several orders at once (one task each). The pick task is its own record, listed under the order in Connections, *Picking*. Nothing is added to the till, to a print layout or to a report.

**What leaves the retailer's iVendNext.** One address: the partner's service (the manifest ships a test address; the partner writes its own, and the retailer's server must trust its certificate). On each press iVendNext sends that service, signed, the order's name, its customer, its warehouse and delivery date, and each line's item code, quantity and warehouse. The consent the System Manager reads in step 3 lists exactly these fields. There is no webhook and no till key. The feed *PP PCK Pick feed* sends nothing: it is where the install names the app's own user, and it installs switched off and stays off. The service writes back with the integration user's key from step 2: it can read and create pick tasks, and it does not read the Sales Order.

## The files

| File | What |
|---|---|
| `manifest.json` | the pick task and its lines, the Connections link, the service (`extension_subscriptions`, extension point `desk_action`) and the button (`desk_actions`), installed **switched off** |
| `route.py` | **the pure core**: the signature check, the press's shape, the task for one order (lines in walking order; quantities arrive in thousandths), the answer |
| `service/app.py` | the HTTP service (standard library): `POST /press/route`, `GET /health`; the record API as the integration user |
| `tests/test_service.py` | laptop tests: the real service, a stand-in record API, presses signed as iVendNext signs them |
| `tests/test_many_shops.py` | many retailers: each retailer's own secret and key, a press before the shop's key arrives, two copies receiving one press, the record type names under the library's prefix, the function entry |
| `tests/canaries.py` | each test that guards a secret, a retailer or the claim goes RED when its check is removed |
| `app.json` | how CitiXsys hosting runs it: a function, paid per call, packaging only the files it needs |
| `tests/test_contract.py` | every answer, and every press our test site recorded, against the published contract (`desk_action.v1.schema.json`) |

The recipe is `recipes/desk_action.md`.

## How to run it

Start the service on your server, under your own process manager: `python3 service/app.py service/.env.local`. Install the manifest in the retailer's iVendNext. It installs switched off: the retailer's System Manager reads what is sent, ticks the consent, and switches the service and then the button on (the recipe has the steps).

To start the service, run this with its settings in `service/.env.local`:

```bash
cd samples/s16_pick_route
python3 service/app.py service/.env.local
```

## Many retailers, hosted

The App library's *Pick route* runs this same `service/app.py` for every retailer that installs it, as a function on CitiXsys hosting (`app.json`): it costs nothing between presses. Set `IVN_LIBRARY_APP` (the library's id) and a shops store (`IVN_SHOPS_TABLE` on hosting, `IVN_SHOPS_FILE` on your own server), and `PCK_PREFIX` when the library's record names differ from the sample's (`IVENDNEXT PCK`).

1. After its install the retailer's site connects itself (the app template's handshake, guide chapter 14b): the service stores the retailer with its library key and the press's secret, `<app>:sub:route`.
2. The install made the app's own user, and the retailer's site hands the service that user's key (`user:<email>`) when it connects, after the install or an update. *Connect again* is only for when the site could not reach the app, or a key was lost or changed.
3. Each press names its retailer (`X-iVendNext-Site`). It is checked with **that retailer's** secret and the task is written with **that retailer's** user's key. Another retailer's secret, or a retailer the service does not know, is refused (401).
4. A press before the key arrives (step 2) is answered in words: *Pick route is not set up yet.* A retailer whose iVendNext refuses the user's key is told to check the user, its role and its API key. A press of more than 20 orders is told to select fewer. Nothing is written.
5. Two copies of the function can receive the same press (a user who presses again while the first is slow). The first takes a short **claim** on the press in the shops table (one conditional write, `claim` in the template's stores); the second is refused (409) and iVendNext tells the user to check the record. A claim left by a copy that stopped is taken over after a minute. After a write iVendNext never answered, the claim is kept for that minute on purpose.
6. The uninstall says goodbye and the service forgets the retailer.

## Before you copy it

- **Order of the lines.** The lines are sorted by warehouse, then item, not by bin. If you have bin data (the S2 bin-location sample), sort by bin instead.
- **What your service may do.** It can read and create pick tasks, and nothing else. It does not read the Sales Order: everything it needs arrives in the press.
- **A pressed-twice button makes one task.** A retry from the same dialog finds the task already made and answers about that task, even after a restart. While one call handles a press, a second call with the same key is refused: in one process by a lock, across copies by a claim in the shops table (*Many retailers, hosted*).
- **One rare double, for one process.** If iVendNext saves a task after your service stopped waiting for it (3 seconds), a retry can make a second task. Many retailers' copies close it: the claim stays for a minute after a write with no answer, so a retry in that minute is refused and a later one finds the task. For one process, keep a lock in your own database if you cannot accept it.
- **At most 20 orders a press, in both modes.** Each order is one write to iVendNext, and a hosted function stops at 10 seconds. A press of more orders is answered in words and writes nothing. Desk waits for the service's `timeout_seconds` (5 here, at most 10): the App library's copy declares 10 so a full press is answered in time.
- **What is sent.** The press includes the `customer`. The service only copies it onto the task; you can stop sending it and fetch it on the task instead.
- **Test routes.** Delete `/test/mode` and `/test/received` from your copy.
- **Your address.** Write your own address in `allowed_urls`. The retailer's server must trust your certificate: a real one for a retailer.

## Technical notes

### What was walked, and where

The GIF: frame: Desk, a 1440-wide window. Walked on our test bench on 2026-10-10, iVendNext POS app at `87812e141`. Built from the same screens as the stills, uncropped.

The stills: walked in a real browser on our test bench, 2026-10-10, iVendNext POS app at `87812e141`. Frame: Desk, a 1440-wide window. The names are the kit's demo site, *Demo Retail*: a stock user (*Nomsa Zulu*), a customer's order, and a colleague picked as the picker (Sipho Dlamini's login, at the demo site's address `demo-retail.example`). The order's lines are priced from the bench's rupee price list, so Desk shows them in INR beside the rand totals; the route does not depend on the currency.

On our test bench the real button was pressed through `ivendnext_mpos.api.desk_action.run`, as a Stock User, on every case in the recipe. `tests/test_contract.py` checks every press the bench recorded.

### Why it is built this way

| Option | Cost | Verdict |
|---|---|---|
| Do nothing (a partner reads the spec) | 0 | the reference apps (quick-commerce hub, 3PL) have nothing to copy |
| One file that answers without writing (a message only) | ~40 lines | shows no real work: the point of a Desk action is that the partner's service does something |
| **A pure core + a standard-library service that writes one record over the API** | ~250 lines | **picked**: the smallest thing that shows the whole loop, signature to record, in code any Python developer reads unaided |

**Idempotency without a database.** The press's `idempotency_key` is stored on the task (`press_key`). A retry from the same dialog finds the task it already made and answers about **that** task (its picker, even if the user changed the dialog), even after a restart. One process serialises presses with a lock; copies serving many retailers take a claim on the press in the shops table (one conditional write), so a retry racing its first try cannot make two.

| Hosting (many retailers) | Cost | Verdict |
|---|---|---|
| A container, one copy, the lock above | about $12 a month | holds, but pays all month for a button |
| A function limited to one copy (`max_copies = 1`) | about $0; no code | holds, but one retailer's press waits behind every other retailer's, and a waiting one is turned away |
| **A function and a claim in the shops table** | about $0 between presses; ~30 lines in the template's stores | **picked**: press-only apps run as functions; the claim holds across copies and only for the same press |

### Bounds, stated

- **Aisles.** The spec's worked example routes by bin. This sample orders the lines by warehouse, then item, and says *"N lines across M warehouses"*. A partner with bin data (the S2 bin-location sample) orders by bin instead.
- **The service's own rights.** The pick task's permission rows give the app's integration role (`PP PCK Integration`, made by the install) **read and create**, and nothing else. The integration user does **not** read the Sales Order: everything the service needs arrives in the press.
- **A create that times out but lands later.** If iVendNext's record API commits a task after the service gave up waiting (3 seconds), a retry that looks before it lands makes a second task. With many retailers the claim on the press is kept for a minute after such a write, so a retry in that minute is refused and a later one finds the task; one process keeps the rare double. If iVendNext saves the task more than a minute late, it still gets two.
- **The claim relies on a press shorter than a minute.** On hosting a function stops at 10 seconds. On your own server a press can run longer (each write waits up to 3 seconds), and a press past `CLAIM_STALE` can be taken over; the file store also serves one process only. Run one process there, or raise `CLAIM_STALE`.
- **A claim left behind.** A copy stopped mid-press, or a write with no answer, leaves its claim as a row of the shops table. It is taken over after a minute and never removed; it names the retailer's site and a hash of the press key, nothing else.
- **What is sent.** `send_fields` follows the spec's worked example, including `customer`. The service only copies it onto the task; a partner who wants to send less can drop it and use `fetch_from: sales_order.customer` on the task's field instead.
- **The contract test** reads the extension points' contract files in [`contracts/`](../../contracts/README.md), which ship in this repository.
- **Picking a colleague.** iVendNext checks the picker as the user may pick it (the same check as the user's own search). On our bench the button's tests picked the user who pressed; the walk of 2026-10-07 picked a colleague (step 2 above) and the task was made with that picker.
- **Test routes.** `/test/mode` and `/test/received` exist only when the process starts with `PP_TEST_MODES=1` **and** the caller sends the admin token. A partner's copy deletes them.
- **`allowed_urls`** names the address of the sample's service (the manifest ships a test address). A partner writes its own. The retailer's server must trust the certificate: a real one for a retailer.
