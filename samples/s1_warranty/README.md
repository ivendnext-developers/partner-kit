# S1 — warranty check (`pp_wrc`), connected leg

![A covered phone sold at the till, and the warranty service's comment on the sale](screenshots/s1_flow.gif)

*A phone is sold at the till with its serial number scanned; seconds later the warranty service's comment is on the sale in Desk.*

This sample is a small Python service that registers a warranty for every covered item a shop sells, and tells staff on the sale. A sale that is a return, or a consolidated roll-up of till sales, registers nothing, and the sale webhooks themselves were not exercised by its tests. It runs on your own server, outside the shop: a developer new to iVendNext can copy it to react to any booked sale without putting code inside the shop.

**When to use it:** you want to do something with every booked sale (register it, notify someone, audit it) and show the result to staff on the sale itself.

## What it looks like

The phone is the sample's own test item (`PP-WRC-PHONE`, covered for 24 months by `service/terms.json`). The comment is signed by the shop's integration user, *PP Integration*.

| Step | Frame | Screenshot |
|---|---|---|
| 1. A sale on the till: the covered phone and a leather case, for a named customer | the till, 1440 wide | ![](screenshots/01_till_sale.png) |
| 2. The till asks for the phone's serial number before it charges | the till | ![](screenshots/02_serial_capture.png) |
| 3. The sale is booked (here with a demo card) | the till | ![](screenshots/03_sale_booked.png) |
| 4. The warranty service's comment on the sale: one warranty, until 2028-10-10; the case not covered | Desk | ![](screenshots/04_warranty_comment.png) |

## What the shop does

A shop that wants a warranty registered for every covered item it sells does this, in the order it meets it:

1. **Install the package (optional).** The shop's administrator opens **Retail Extension Package** in Desk, pastes `manifest.json`, presses **Check**, reads the summary, ticks the consent and installs. It adds one record type, `PP WRC Warranty Term`, and a **Warranty terms** workspace. It adds no role: the record type is open to the shop's own System Manager and Retail Manager.
2. **Enter the terms.** In the **Warranty terms** workspace a System Manager or a Retail Manager adds one `PP WRC Warranty Term` for each covered item or item group: **Applies to** (*Item* or *Item Group*), the item or the group, and **Months**. An item's own term wins over its item group's. The service in this folder keeps the same kind of terms in its own file, `service/terms.json` (item or item group, and months).
3. **Make the service's own user.** The administrator makes one integration user for the service, holding one narrow role, as the [integration user recipe](../../recipes/integration_user.md) describes: read on the shop's sales (*Sales Invoice*, *POS Invoice*), items and serial numbers on a sale (*Serial and Batch Bundle*), and the right to add a **Comment**. Its API key goes to the service. The comment on the sale is signed by this user.
4. **Have the shop call the service on every booked sale.** A System Manager creates a **Webhook** for *Sales Invoice* and for *POS Invoice* on **Submit**, with **Enable Security** on, a long **Webhook Secret** (the service holds the same one) and a thin JSON body that names the record and when it changed ([`recipes/webhook_receiver.md`](../../recipes/webhook_receiver.md)). Its address is the service's `/webhook`.
5. **Sell.** The cashier sells a covered item and scans its serial number, as the till asks. Within seconds the service's comment is on the sale in Desk: one warranty per covered serial number, and a line for each item not covered.
6. **Optional: the "Warranty" till key.** A System Manager adds a **Retail Remote App Key** record in Desk: the partner's name, an app name, the key, its label, *message* as the only thing it may return, the service's HTTPS address (`/point/warranty`), a signing secret both sides hold and the time to answer. The manifest declares no till key, so this record is made by hand: tick it enabled and tick the customer's consent. Then the store switches the key on in **POS Studio > Apps**.

**Where it shows.** In Desk: one Comment on each covered sale, and the **Warranty terms** workspace if the package is installed. At the till: the serial-number prompt, and with the till key a short message titled *Warranty* that names each item and its months. In POS Studio: the key, under **Apps**. No print layout, report or number card.

**What leaves the shop.** The manifest alone sends nothing: it names no outside address, webhook, till key, event-feed registration or service. The connected form does send, on your own server:
- the **webhook** sends the service a signed message that names the record and when it changed, and nothing more (record type, name, event, time, company);
- the **service** then reads the sale's lines and their serial numbers with the integration user's key, and writes one Comment on the sale; nothing else is added to the shop;
- the service keeps, in its own store outside the shop, each warranty's serial number, item code, sale name, months and dates, and the sales it has handled;
- with the till key, each press makes the till's server send the service the sale's context: the item codes, quantities and units, the store, the customer on the sale, the cashier, the sale's reference, the register's profile, the company and the currency. No prices, totals, payment details or serial numbers. The service reads the items' groups with the same key.

## How it works

When a sale is booked in iVendNext, this small Python service, running on the partner's own server:
1. receives the signed webhook and checks it ([`recipes/webhook_receiver.md`](../../recipes/webhook_receiver.md));
2. reads the sale's lines and their serial numbers over the record API, as an integration user;
3. registers a warranty per covered serial number in **its own** store (SQLite), using **its own** terms;
4. writes **one Comment on the sale**, which staff see on the sale in iVendNext Desk.

A reconciliation pull finds every sale whose webhook never arrived. Nothing is added to the shop's database except that Comment.

## The files

| File | What |
|---|---|
| `core.py` | **The pure core.** `warranty_answer(context, terms)` gives the till's answer, `registrations(...)` the warranties of a booked sale, and `comment_text(...)` the Comment. It imports no framework. `context` is shaped exactly like the till's app-button context, and the answer uses only the till's closed vocabulary, so the same file can be bound at the till unchanged |
| `service/app.py` | the HTTP service (standard library): `POST /webhook`, `POST /reconcile` and `GET /status` (both need `X-PP-Admin`), `GET /health` |
| `service/receiver.py` | signature check and the replay key |
| `service/tenant.py` | the only door into iVendNext: the record API calls of `api/collection/` |
| `service/store.py` | the partner's own store: terms, warranties, handled sales, seen-set, watermark, events |
| `service/terms.json` | the partner's warranty terms (item or item group → months) |
| `tests/test_core.py` | tests of the core on recorded sale contexts (`tests/contexts/`) |

## Two ways to use the same core

Outsiders never write Python inside a shop's site. Both forms below run on your own server, and both are public: an iVendNext Partner may build either.

| Form | What | Who may use it |
|---|---|---|
| **Connected** — `service/` | the partner's own service: reads booked sales (a webhook nudges it today; the reliable route is now the event feed, [`recipes/event_feed.md`](../../recipes/event_feed.md)), keeps warranties in its own store, comments on the sale | **public** — the form an iVendNext Partner builds |
| **Remote till key** — `remote/wrapper.py` | the same pure core answering the till's "Warranty" key from the partner's own server (the remote key contract) | **public** |

## Run it

```bash
python3 -m unittest discover -s samples/s1_warranty/tests -p 'test_core.py' -v
```

```bash
python3 samples/s1_warranty/service/app.py samples/s1_warranty/service/.env.local
```

The service reads one env file (never committed; `chmod 600`), kept at `samples/s1_warranty/service/.env.local`: `PP_BASE` (the shop's address), `PP_KEY` and `PP_SECRET` (the integration user's API key), `PP_WEBHOOK_SECRET`, `PP_ADMIN_TOKEN` (for `/reconcile` and `/status`), and optionally `PP_PORT` (8121), `PP_DB`, `PP_TERMS`, `PP_SINCE` and `PP_RECONCILE_SECONDS`. Run it on a server that stays up, so no delivery is dropped; the shop's webhook points at its `/webhook`.

## What is refused, and why

The service refuses a delivery whose signature does not check, and a delivery it has already seen (a replay). That way nobody but the shop can make it register a warranty, and a sale delivered twice is handled once.

A sale that is a return, or a consolidated roll-up of till sales, registers nothing.

## When your service is down

A sale booked while your service is down is not lost. The reconciliation pull (`POST /reconcile`) finds every sale whose webhook never arrived. Run it nightly and after every restart.

## Technical notes

### The walk

The GIF: a cashier sells a covered phone and a leather case to a customer, scans the phone's serial number, and takes the card; seconds later the warranty service's comment is on the sale in Desk: one warranty registered, the case not covered. Frames: the till (`/pos?frame=terminal`, 1440 wide), then Desk. Walked on our test bench on 2026-10-10, iVendNext POS app at `87812e141`. Built from the same screens as the stills below, uncropped.

The stills: walked in a real browser on our test bench, 2026-10-10, iVendNext POS app at `87812e141`. The shop is the kit's demo shop, *Demo Retail*. The cashier is the bench's *Thabo Nkosi*, the customer *Naledi Khumalo*; the phone is the sample's own test item (`PP-WRC-PHONE`, covered for 24 months by `service/terms.json`). The comment is signed by the shop's integration user, *PP Integration*. Step 3's card is the bench's demo card.

### The tests

| File | What |
|---|---|
| `tests/test_core.py` | core tests on contexts **recorded** from the bench's own `build_context` (`tests/contexts/`) |
| *our test bench's own run (not in the kit)* | the end-to-end tests: functional, signature, replay, idempotency, three failed deliveries → reconciliation |
| *our test bench's own run (not in the kit)* | a canary that proves the end-to-end tests can fail: a receiver with no signature check and no replay set must turn them red |

On our test bench the service ran beside the shop and passed its end-to-end test (signed delivery, replay refused, reconciliation).

### The two forms

The forms table dates from 2026-10-04 — the rule: outsiders never write Python inside a tenant. The remote till key was, on our test bench, pressed through the released key over HTTPS on 2026-10-07: through the till's own press endpoint, called from the bench's console as the cashier, not from the till's screen. A press of *Warranty* from the till's screen or from a physical till device was not tried.

### The env file's path

`service/app.py` opens the path it is given from the current directory (`load_env`, `open(path)`), so from the kit's root the command passes `samples/s1_warranty/service/.env.local`. The remote binding reads the same file at that place (`remote/wrapper.py`: `os.path.join(SAMPLE, "service", ".env.local")`), so keep it there. Our test bench runs the same command from the sample's own folder as `python3 service/app.py service/.env.local`.

### Why it is built this way (R6)

| Option | Cost | Verdict |
|---|---|---|
| **Standard library only** (`http.server`, `urllib`, `sqlite3`) | ~300 lines; nothing to install on the partner's server or the test machine | **picked**: any Python developer reads it unaided |
| Flask or FastAPI | shorter handlers; a virtual environment and dependencies on the test machine | rejected for a reference sample |
| A generated client from `api/openapi.yaml` | adds a build step; the calls are six plain HTTP requests | not needed (G3 makes it optional) |

### Bounds, stated

The reconciliation timer is off on the bench (`PP_RECONCILE_SECONDS=0`) so the tests drive it. A partner runs it nightly and after every restart. A sale that is a return, or a consolidated roll-up of till sales, registers nothing. POS Invoice webhooks are subscribed but not exercised by these tests, which open no POS day.
