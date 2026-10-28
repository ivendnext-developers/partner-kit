# S40 — Expiry and recall (`pp_rcl`): recalls, disposal on the record, goods-in

*Start from this sample: `python3 tools/manifest/start.py s40_expiry_recall --prefix "ACME RCL"` copies it into `apps/` of your repository under your own prefix (your company's first word, then a short name for the app) and checks it ([how](../../recipes/make_it_your_own.md)).*

A pharmacy, a grocery or any retailer that sells lots with an expiry date. Four jobs, one small service:

- **A recall.** The regulator names lots. A Recall Officer enters the notice and presses **Block these batches**: each lot is switched off at every till and store at once, each store's stock of it is found, and, at consumer depth, so is every customer it already reached.
- **Disposal.** Recalled or expired stock moves to the quarantine store by the retailer's own transfer. Its disposal issue is refused unless it names a **Disposal Record** carrying the regulator's visit (officer, authority, date, signed form); the record then locks.
- **The worklist.** An **Expiry Worklist** lists, per store, the lots that expire within the retailer's window, and the medicine lots with no expiry date at all.
- **Receiving.** A goods receipt is refused when a lot has fewer days left than the retailer's minimum, unless its line carries a **Letter of Undertaking** with its days. An ERP's own receipts are flagged, never refused.

Kit sample **S40**; its App library copy is `ivendnext_rcl`. Part of iVendNext's pharmacy standard version, and useful to any retailer that sells by lot.

## What happens

| When | What happens |
|---|---|
| **Block these batches** on a recall notice | each lot gets `disabled` (the till's automatic lot read drops it at once), except a lot of an item with *Has Expiry Date* and no expiry date: that one is left as it is and named, because saving it would make iVendNext write a guessed date into it (or refuse); the notice gets each store's stock of the lots, read from the stock ledger, and, at consumer depth, the customers supplied (a till sale, a Desk invoice, a delivery; a till sale is listed under its POS sale until its day closes, then under the day's merged invoice, never twice); a **Store Progress** record per selling store holding the lots (not the quarantine stores); the clock (start by, complete by) from the class's settings where the notice has none. *"Blocked 2 lots. 1 not blocked: no expiry date (enter the pack's, then press again). Stock found in 2 stores; 3 sales to 3 customers."* |
| the same press again | nothing is written to a lot again; the stock and customers are read afresh (a sale that synced from an offline till since shows up); a store's own status and quarantined quantity are kept |
| **Refresh** on a worklist | its lots near expiry (with stock, within the window, per store, past-dated included) and its medicine lots with no expiry date, each marked when a recall notice names it (that lot stays blocked); the action the pharmacist chose on a lot is kept |
| a goods receipt is submitted (Desk, import, API) | refused: a lot with fewer days left (counted from today, or the posting date if later) than the item's or the retailer's minimum, unless its line has a Letter of Undertaking for at most the days it has; an expired lot, always; a Letter of Undertaking with no days; a lot of an item with a shelf life until *Pack expiry* is typed on its line (iVendNext can work such a lot's expiry out, and a later edit leaves no trace), or one that does not match it; a line with no lot (a line rejected whole is not judged); no supplier's invoice number when the settings ask. By the ERP connector's own user: submitted, the problems written into *Receiving check* |
| a stock entry is submitted | refused when it disposes of a witnessed item without a Disposal Record for the line's store whose visit is recorded on or before the posting date, that is locked, and whose lines still cover the lot and quantity (in the stock unit) after what earlier issues drew on it. A disposal is stock of the item written off (an issue, a consumption, a repack or manufacture whose finished line is not itself a witnessed item), or stock leaving a quarantine store, or a blocked or expired lot, for anywhere but a quarantine store. With no quarantine store in the settings, every such disposal is refused, saying so; other movements go on |
| a stock entry is posted by the ERP connector's own user (SAP brings its receipts and disposals as stock entries, every few minutes) | not refused for what it holds: its incoming lots are judged as a goods receipt and its disposals as above, and the problems are written into the entry's *ERP check* field (it is refused only when the app itself cannot run: no settings, or its user refused). A Desk *Material Receipt* (opening stock, adjustments) is not judged: goods-in is the purchase receipt |
| a stock count is submitted | refused when it lowers a witnessed item's stock in a quarantine store, or of a blocked or expired lot: a count never disposes; issue it naming its Disposal Record |

## What the retailer does

**Before you install:** every `host.docker.internal` address in `manifest.json` (in `allowed_urls`, and where the manifest calls it) is our test bench's own address for the sample's service, and it resolves only where Docker provides it. Replace it with your own service's address first, or iVendNext's calls never reach your service; if this manifest is already installed, raise its `version` and install it again ([the manifest recipe](../../recipes/manifest.md), step 6).

1. **Install** the manifest. It installs switched off.
2. **The app's user:** from POS 2.1.0.667 the install made the app's own user, `pp_rcl@integration.invalid`, and named it on *PP RCL Recall feed*; it holds the role *PP RCL Integration* alone, works through the API only and can never sign in to Desk. Give that role read on Item, Serial and Batch Bundle, POS Invoice, Sales Invoice, Delivery Note, Stock Entry and Retail Save Rule, and read and write on Batch (it writes `disabled` only). Leave the feed switched off. A service for one retailer: press *Generate Keys* on that user (User, API Access) and put the key in the service's settings. A service for many retailers is handed the key by the retailer's site itself, after the install or an update; press *Connect again* only if the site could not reach the app, or a key was lost or changed.
3. **The settings record `Default`:** your site's time zone (hours from UTC); the minimum shelf life at receipt; whether the pack's expiry is required where an item has a shelf life (untick it, and the supplier's number, if you receive on Handheld, which can send neither); the near-expiry window; the quarantine stores; the ERP connector's own users (never a person's login); each class's clock and depth (the defaults are Kenya's PPB table: 24 h / 14 days, 72 h / 21 days, 5 days / 28 days); and who needs the regulator's visit (by the items' schedules: *Pharmacy counter rules*' field by default; *Every disposal*; or *No disposal*).
4. **People:** give *PP RCL Recall Officer* to whoever runs recalls and disposals.
5. **Switch on:** the five services (read what each sends, tick the consent), the two buttons, and the five save rules on the Disposal Record. ⚠ Until the lock rule *PP RCL disposal locked once the visit is recorded* is on, every disposal is refused: a record that can still change proves nothing.
6. **The prints:** in the print view, choose *PP RCL Recall Report* for a notice (the report for the regulator) and *PP RCL Disposal Record Print* for a disposal, and set each as the default (*Customize Form*, Default Print Format: a manifest may not set it). ⚠ On a retailer's iVendNext whose release lacks the product's fix, these two prints do not print yet: `/printview` answers 404 and Desk's preview keeps the standard layout ([guide chapter 7](../../guide/07_manifests.md#a-print-format-on-your-own-record-type-a-known-defect)).
7. **Daily list of lots with no expiry:** the report *PP RCL Lots with no expiry date* by e-mail, daily (the retailer's own *Auto Email Report*).

## The files

| File | What it is |
|---|---|
| `manifest.json` | five record types and six tables, seven fields on the retailer's records, two Desk buttons, three document checks (receipt, stock entry, stock count), a workflow, five save rules, two reports, two prints, a reminder, the feed registration |
| `recall.py` | the pure core: the signature, the recall's outcome per lot, stock per store, customers supplied, the clock, the worklist, the receiving and disposal rules, the answers |
| `service/app.py` | the service: five routes, one per door, each signed with its own secret; the retailer's record API as the app's user |
| `app.json` | hosted as a function, paid per call |
| `tests/` | 98 laptop tests against a stand-in iVendNext, and 63 canaries (`canaries.py`): each guard's test goes red when its check is removed |

## Run it

```bash
python3 -m unittest discover -s samples/s40_expiry_recall/tests -p 'test_*.py'
python3 samples/s40_expiry_recall/tests/canaries.py
python3 samples/s40_expiry_recall/service/app.py samples/s40_expiry_recall/service/.env.local
```

One retailer's `.env.local`: `PP_BASE`, `PP_KEY`, `PP_SECRET` (the app's user) and the five secrets the install handed back once, `PP_SECRET_BLOCK`, `PP_SECRET_WORKLIST`, `PP_SECRET_RECEIPT`, `PP_SECRET_DISPOSAL`, `PP_SECRET_COUNT`.

## Many retailers, hosted

`IVN_LIBRARY_APP=ivendnext_rcl` with a shops table (`IVN_SHOPS_TABLE` or `IVN_SHOPS_FILE`), and `RCL_PREFIX=IVENDNEXT RCL`: each retailer connects itself (the app template's handshake, guide chapter 14b), each call is checked with that retailer's own secret for that door, and read and written with that retailer's own key. The service keeps nothing between calls.

## Make it your own

What a partner usually changes:
- **the rules:** a market's recall clocks and depth (they are settings); a witness that is not the regulator; a minimum shelf life per supplier; a returns-to-supplier flow from the worklist;
- **the trace:** customers' phone numbers on the notice for a call list (health data: decide who reads it);
- **the prefix:** `tools/manifest/rename.py` makes your copy under your own reserved prefix; the service takes it from `RCL_PREFIX`;
- **its records:** `tools/deploy/copy_records.py` moves the settings record between a test site and the retailer's iVendNext.

## Before you copy it

- **A Desk document that names a blocked lot by hand is refused from POS version 2.1.0.666.** The till's automatic lot read drops a disabled lot, so the online till never offers it; from 2.1.0.666 the POS app also refuses a disabled (recalled) lot, and an expired one while the retailer's *Allow Selling an Expired Batch* is off, on every outgoing stock document, from Desk, an import or the API: a Delivery Note, a Sales Invoice that moves stock, a Stock Entry, a POS Invoice submitted outside the till. A Material Issue, a move into a quarantine store and a return to the supplier still pass, so the disposal check above still guards the disposal. On an older POS app such a Desk document still submits ([chapter 9](../../guide/09_points_and_requests.md), *A lot that may not leave the shop*).
- **An offline till keeps a blocked lot until it next syncs**, and a sale it made offline is traced at the next press.
- **A lot with no expiry date is never blocked by the app.** Enter the date printed on the pack, then press again.
- **The customers supplied are health data.** The notice is readable by the Recall Officer and System Manager only; the store's staff work their Store Progress record.

## Technical notes

### Why it is built this way

- **The ledger, not the lot read.** The retailer's own lot read returns nothing for a disabled lot, so a second press would find no stock. The service reads the stock ledger's lot rows (the bundles) instead, leaving out a POS sale's own bundle (it books no stock until the day's sales are merged) and anything cancelled.
- **Never save a lot with no expiry.** With *Has Expiry Date* on and a shelf life set, iVendNext fills a missing expiry from the manufacturing date (which defaults to the day the lot was entered) plus the shelf life. That is a guess, early or late. The same arithmetic is why the receipt asks for *Pack expiry* when a lot's expiry equals it.
- **Checks, not screens.** Both rules are document checks, so they hold on the Desk, an import and the API alike. The check is not told the channel; the ERP's own user is how it knows a receipt came from the ERP, and *fill* is how it flags one without stopping the feed.
- **Down answers.** All three checks refuse when the service does not answer: the retailer's own refusal of an expired lot reads only a line's own lot, against the posting date, so it is no net. While the service is down, receipts, stock entries and counts wait, **the ERP connector's included: SAP's five-minute stock sync stops until the service answers again** (the connector logs each refusal). A retailer that would rather keep its ERP sync running sets the stock-entry check's down answer to *allow and flag* in its subscription, and then a Desk disposal goes through unwitnessed during an outage, flagged in the Extension Log.

### Bounds, stated

- Handheld's receiving path is not proven here. Its receipt cannot send the supplier's number, and a lot it receives with a typed expiry passes unless that date happens to equal the manufacturing date plus the shelf life.
- A schedule set only on an item group (Pharmacy counter rules' group default) is not read: give the controlled item its own schedule row, or choose *Every disposal*.
- A lot made automatically during a receipt's submit is not visible to the check, so the line is refused: make the lot first, with the pack's expiry.
- An issue refused because the visit was not yet recorded, submitted again unchanged within 5 minutes, gets the same refusal: iVendNext answers the same document, fields and user from its last answer for 5 minutes (the document check's *asked once*). Submit it again after that.
- A disposal by a return to the supplier (a purchase return) is not checked: it is the supplier's, not a destruction.
- iVendNext answers the same document from its last answer for 5 minutes, and is sent a line's bundle, not the bundle's lots: a lot swapped inside the same bundle within those 5 minutes is not asked about again.
- A retailer that disconnects the app (its key) has every check answered by its down answer: refused.
- A recall that reaches thousands of sales may not finish within Desk's 10 seconds; the lots may already be blocked. Press again: it is safe, and quicker.
- One *Pack expiry* per receipt line: a line holding lots of different expiries is split.
- Two disposals against one record submitted at the same moment each read what earlier issues drew before the other commits, and can together over-draw it; the register (the POS app's controlled-stock door) shows both.
- The lock is read as the save rule's switch, mode, states, fields and bypass roles. A System Manager who edits the rule in other ways is the retailer's own control.
- The settings' hours from UTC decide *today*; leave it blank and the retailer's day is UTC's (a receipt late in the evening in Mexico City is judged on the next day).
- A count that lowers good stock of a controlled item in a selling store is shrinkage, not a disposal: the controlled register records it.
- A store holding a negative quantity of a recalled lot is left out of *stock found*.
- Unblocking a lot after a recall is lifted is manual (untick *Disabled* on the lot); nothing stops it while another open notice names the same lot.
- The report *Lots with no expiry date* lists every lot without one, medicine or not (a report filters only the lot's own fields); the worklist lists medicine lots only.
- *Shelf-life check exempt* and the Letter of Undertaking can be ticked by whoever receives: a field a kit app adds cannot be limited to a role.
- Not built here, for later or for a partner: a near-expiry notification (sample S27 sends one), an overdue mark on store progress, the release or return of recalled stock to the supplier per lot, the chain of custody to destruction, per-store progress inside the regulator's print (a print reads only its own record: the *Recall progress* report has it), and a recall's effectiveness check.
- Lots on one notice: at most 100.
