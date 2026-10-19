# S2 — bin locations (`pp_bln`): where stock sits inside a store

![The bin locations workspace, the bins and what is in each](screenshots/s2_flow.gif)

*The bin locations workspace in Desk: the bins on their aisles, and what is in each bin.*

S2 records only **where** items sit inside a store — locations (back room, shop floor), aisles, bins and what is in each bin — and answers the cashier's **"Where is it?"** key. The shop's stock and valuation stay in iVendNext. It is for a developer who wants to add their own records and screens to a shop, kept up to date by their own service.

**When to use it:** your product keeps its own data beside the shop's (here, bins) and staff should see it in Desk and at the till.

## What it looks like

| Step | Frame | Screenshot |
|---|---|---|
| 1. The workspace the manifest installs: locations, bins, what is in each bin | Desk, 1440 wide | ![](screenshots/01_workspace.png) |
| 2. The bins, each on its aisle | Desk | ![](screenshots/02_bins.png) |
| 3. What is in each bin: the quantities the service keeps from booked sales and stock movements (here one row: 6 put away in the back-room bin) | Desk | ![](screenshots/03_what_is_in_each_bin.png) |

Quantities in Desk's bin list show three decimals (`2.000`, and `0.000` for an empty bin; the step 3 picture shows a whole number in its report): Desk draws a Float field to the system's float precision, which is 3 unless the shop changed it. The bins hold what the service writes; the extra zeros are the display. A field may set its own `precision`; this sample leaves that to the shop. (Seen on a test shop; not re-measured with another setting.)

The names are the sample's own placeholders (`PP Durban Floor F1`, `SF-F1-01`). The till key *"Where is it?"* is not shown: on our test bench it installed switched off (see below).

## What the shop does

A shop that wants to know which bin an item sits in does this, in the order it meets it:

1. **Install the package.** The shop's administrator opens **Retail Extension Package** in Desk, pastes `manifest.json`, presses **Check**, reads the summary (it lists the two outside addresses below), ticks the consent and installs. The role **PP Integration** is not made by the install (it does not start with the app's prefix): **the shop makes it before installing**. The install adds five record types, a field on the Item record, a bin label, the **Bin locations** workspace, two webhooks and the till key *"Where is it?"*. The install shows each secret once: the two webhooks' and the till key's. They go to whoever runs the service.
2. **Make the service's own user.** The administrator makes one integration user for the service ([integration user recipe](../../recipes/integration_user.md)), gives it the role **PP Integration**, made before the install (User record > roles), and generates its API key for the service. The role holds the rights on the bin records; the reads on the shop's own records (sales, items, warehouses, stock balances, POS Profile) are the ones the recipe lists.
3. **Describe the store.** In **Bin locations > Locations** a System Manager adds one location for each back room and shop floor: **Location**, **Kind** (*Back room* or *Shop floor*), **Warehouse** (where the stock is booked) and **Store it serves** (the till's selling warehouse).
4. **Add the aisles.** A System Manager adds each aisle as a `PP BLN Aisle` (search for it): its name and its location.
5. **Add the bins.** In **Bin locations > Bins** a System Manager adds each bin: **Bin** (its code) and its **Aisle**; the location follows from the aisle. The bin label is the `PP BLN Bin Label` print format on a bin; a Retail Manager may print it.
6. **Put stock in the bins.** Nobody types what is in a bin: **What is in each bin** is kept by the service, from putaways, picks and booked sales. Stock must already be received into the back room's warehouse; the service's putaway puts it in a back-room bin, and its pick moves it to a shop-floor bin of the till's own store. A booked sale then takes its items off the shop-floor bins of the store it sold from. A Retail Manager reads all of it and changes none of it.
7. **The till key.** From the release that carries it, a till key the manifest declares is ready in **POS Studio > Apps** as soon as the app is installed: the consent the administrator reads on the install screen is the key's consent, and the store switches the key on there and places it on its till. Until then it installs switched off with consent not given, and the shop's administrator ticks both in Desk (**Retail Remote App Key**). The cashier then presses **Where is it?** on a sale.

**Where it shows.** In Desk: the **Bin locations** workspace (Locations, Bins, What is in each bin), the bin label print format, and a **Default bin (bin locations)** field on each Item. At the till: the *"Where is it?"* key, which answers with a short message naming the bin of each item on the sale (the shop floor first, else the back room). In POS Studio: the key, under **Apps**. No report or number card.

**What leaves the shop.** The manifest names two outside addresses and the service signs in to the shop:
- two **webhooks**, on **Submit** of a *Sales Invoice* and of a *POS Invoice*, send the service a signed message that names the record, the event and the time, and nothing more, to `http://host.docker.internal:8123/webhook` (the sample's own test address);
- the **till key**: each press makes the till's server call `https://bins.partner.example/point/where_is_it` (the sample's placeholder) and wait at most 3 seconds. It sends the sale's context: the item codes, quantities and units, the store, the customer on the sale, the cashier, the sale's reference, the register's profile, the company and the currency. No prices, totals, payment details or serial numbers. The answer is a message only;
- the **bin label**, a print format: a template the shop's own server runs when a bin is printed; it sends nothing out;
- the **service**, with the integration user's key, reads the booked sale, the stock balance of an item in a warehouse and the till profile's warehouse; it writes the bin records, and, for a pick, books one *Material Transfer* **Stock Entry**.

## The till key alone, hosted by CitiXsys (`service/where.py`)

The App library's *Bin locations* (1.1.0) is S2's records with only its till key: no webhooks, no putaway or pick, and a sale does not change a bin. The shop types what sits in each bin, and *Where is it?* tells the cashier where those notes say each item is. `service/where.py` is that key alone, written to serve many shops:

- **What it reads.** On each press, with the app's own user's key, two reads of the shop, each bounded by the till's store: its locations (a location's `store` is the warehouse the till profile sells from), then *What is in each bin* for the sale's first 30 items with a quantity above 0 at those locations. A *What is in each bin* record's **Location** fills itself from its bin when the record is saved (manifest 0.1.1), so a record saved before that field existed is found once it is saved again. It writes nothing, and it does not read an item's default bin.
- **How it knows the shop.** Each shop connects itself after it installs the app (the app template's handshake, guide chapter 14b). The press is checked with that shop's own till key secret (`<app>:where_is_it`); the user's key arrives once the shop chooses that user on the app's feed (`registered_applications`) and presses *Connect again*.
- **What the cashier reads when it cannot answer.** Each is a warning in the key's own message, never a guess: before *Connect again*, *Bin locations is not set up yet*; when the shop refuses the key (401), *check the app's user and press Connect again*; when the user may not read the records (403), *let its role read Locations and What is in each bin*; when the shop does not answer within the shared deadline (2.2 seconds for both reads), *the bins cannot be read right now*; when one read returns more than 1,000 records, *there are too many bin records to answer here*.
- **Its limits.** A record's Location is copied from its bin when the record is saved: after you move a bin to another aisle, save its records under *What is in each bin* again, and a record saved before manifest 0.1.1 is found once it is saved again. The till's message shows about ten items, so a sale's items after the thirtieth are only counted (*and N more*), and such a sale is coloured as a warning. A variant is looked up by its own code: record the variant in a bin, not its template. The time limit is per network step, so a shop that trickles its answer can still pass the till's 3 seconds.
- **How it runs.** As a function, paid per call (`app.json`, `"runs": "function"`): it only answers presses. One shop on your own server: `IVN_POINT_SECRET`, `IVN_SHOP_URL`, `IVN_SHOP_KEY`; many shops: `IVN_LIBRARY_APP` with a store (see the file's header).

Tests: `tests/test_where.py`; their canaries: `python3 samples/s2_bins/tests/canaries.py` (each must be RED).

## Its form (outsiders never write Python inside a customer's site)

| Piece | What |
|---|---|
| `manifest.json` (**v2**) | the data: five record types, the `Item.pp_bln_default_bin` field, display setters, a bin label, a workspace, two signed webhooks to the service — and **the till key as a remote key** (`remote_keys`: "Where is it?", calling the partner's own service over HTTPS; on our test bench it installed switched off with consent not given, and from the release that carries the change it is ready in POS Studio > Apps once the app is installed: see below) |
| `service/` · `core.py` | the partner's own service: keeps the bins up to date from booked sales and answers the remote key from the pure core |

The "Where is it?" key: what it does on install, today and from the release that carries the change, is step 7 of *What the shop does*. It has not yet been pressed on a till; the same kind of key has been, for S1 (through the till's press endpoint) and S6 (on the till's screen).

## What is refused, and why

A shop whose iVendNext POS app does not yet have the released remote till key refuses this manifest at install: the manifest carries a remote key, which such a shop cannot install.

## Run it

```bash
python3 tools/manifest/validate.py samples/s2_bins/manifest.json
```
```bash
python3 -m unittest discover -s samples/s2_bins/tests -p 'test_core.py' -v
```
```bash
python3 samples/s2_bins/service/app.py samples/s2_bins/service/.env.local
```
The env file (never committed), kept at `samples/s2_bins/service/.env.local`, holds `PP_BASE`, `PP_KEY`, `PP_SECRET`, `PP_WEBHOOK_SECRETS` (the manifest's two webhooks, comma-separated), `PP_ADMIN_TOKEN`, `PP_POINT_SECRET` (the remote key's signing secret), `PP_COMPANY`, and optionally `PP_PORT` (8123), `PP_DB` and `PP_SINCE`.

## Technical notes

### The walk

The GIF shows what the manifest installs, as staff see it in Desk: the workspace, the bins with their aisles, and what is in each bin — the quantities the partner's service keeps up to date from booked sales. Frame: Desk, 1440 wide. Walked on our test bench on 2026-10-10, iVendNext POS app at `87812e141`. Built from the same screens as the stills below, uncropped.

In step 3, one row: 6 units put away in the back-room bin. The workspace still (step 1) is from the earlier walk on 2026-10-07; it shows no shop name.

### What was proven where

**On our test bench** the manifest now installs **with** its remote key, switched off and with no consent, as a shop receives it until the release that carries the change (before the bench's POS app had the released key, the installer refused it, and that refusal is tested); the till key was driven by our stand-in caller with the till's real context and the till's real validator. **UNPROVEN:** a press of *Where is it?* on a till. The released key has answered presses for S1 (through the till's own press endpoint, called from the bench's console as the cashier) and S6 (pressed on the till's screen, the iVendNext POS app in a desktop browser); a physical till device was not tried. The release's other behaviour, the key ready in POS Studio > Apps as soon as the app is installed, is not among the things proven here.

### The reconciliation pass reads 200 sales at a time

`POST /reconcile` lists booked sales modified since its mark, oldest first, at most **200 per kind of sale** (Sales Invoice, POS Invoice) per pass, and moves the mark past each sale it handles. Handling a sale twice is safe (the bin records remember each sale). A shop that sold more than 200 between two passes is caught up by running the pass again; a pass that lists fewer than 200 sales of each kind has reached the end. The page size is `limit` in `service/tenant.py`.

### The env file's path

`service/app.py` opens the path it is given from the current directory (`_env(sys.argv[1])`), so from the kit's root the command passes `samples/s2_bins/service/.env.local`. With no argument it reads `.env.local` beside `app.py`, the same file. Our test bench runs it from the sample's own folder as `python3 service/app.py service/.env.local`.
