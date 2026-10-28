# S7 — a system sync: a customer's own ERP, order system or warehouse system in step with iVendNext

*Start from this sample: copy this folder into `apps/<your app>/` of a repository made from the kit and change the names as this page says; the one-command start does not cover it, because it builds its own manifests ([how](../../recipes/make_it_your_own.md)).*

This sample keeps a customer's own back-office system in step with iVendNext. Items, prices and stock go out to iVendNext; booked sales and returns come back, once each; a nightly report names anything the two disagree on. It is for a developer who connects a large customer's ERP, order system or warehouse system to their stores.

Runs **outside** the retailer's iVendNext, over the record API and the event feed ([`recipes/event_feed.md`](../../recipes/event_feed.md)); written up as a recipe: [`recipes/system_sync.md`](../../recipes/system_sync.md).

**When to use it:** another system is the master for items, prices or stock, and it must also learn of every sale.

## What the retailer does

The sample is a tool a customer's IT team runs, not a screen. What the retailer does is small and happens once:

1. **Make the sync's user.** No app is installed here, so nothing makes this user: the administrator makes one integration user for it ([integration user recipe](../../recipes/integration_user.md)) holding this grant: read and write on the feed's log (to mark events done); read on *POS Invoice*; create and write on *Item* and *Item Price*; create, write and submit on *Stock Entry*; read on *Bin* and *Warehouse*. The user's API key goes to the sync.
2. **Register the sync.** The retailer's administrator creates a **Registered Application** for the sync that follows **POS Invoice** ([`recipes/event_feed.md`](../../recipes/event_feed.md), step 1), chooses its integration user and ticks the record type on.
3. **Name the store.** The sync is told the one warehouse and the one company it serves; it serves one of each per run.
4. **Let it run.** Items, prices and stock the ERP changed arrive in the retailer's iVendNext as items, item prices and stock entries iVendNext books. Each sale and return iVendNext books reaches the ERP once.
5. **Read the nightly report.** The reconciliation names, by name, anything the two sides disagree on. It never fixes anything: a difference in money is a person's decision.

**Where it shows.** In Desk: the items, prices and stock entries the sync wrote, and the registered application. At the till and in print: nothing changes. The nightly report is the sync's own output, not a Desk report.

**What leaves the retailer's iVendNext.** There is no manifest. The sync runs outside the retailer's iVendNext, on the customer's own server, with the integration user's key: it reads the event feed's rows and each booked sale and return (the item, quantity and amount on the invoice) and sends them to the customer's own ERP; it writes items, item prices and stock entries into the retailer's iVendNext. It keeps its own working files (the cursor, the identity map and the seen-set). Its feed key is not limited to one application: it can read and mark done every application's rows, and the sample says so.

## How it works

1. **Out:** items, prices and stock — only what changed since the cursor — are written to iVendNext.
2. **In:** booked sales and returns are read from the event feed and written to the ERP, once each.
3. **Reconcile:** a nightly, read-only report, by name, of anything that differs. It never fixes anything.

## The files

| File | What |
|---|---|
| `erp.py` | the customer's ERP as a stand-in: a SQLite file with items, prices per price list, stock movements, the orders and returns it is told about, and a numbered change feed |
| `sync.py` | the sync: **out** (items, prices, stock — only what changed since the cursor) · **in** (booked sales and returns, once each, from the event feed) · **reconcile** (a nightly, read-only report by name) · the identity map |
| `tests/test_s7.py` | 18 tests that run on a laptop: the sync against an in-memory stand-in and feed |

## Run it

No screen shows a sync working, so here is the command. What a test run printed is under Technical notes.

```bash
SYNC_KEY=… SYNC_SECRET=… python3 samples/s7_system_sync/sync.py run --base https://shop.example --app "My Sync" --erp erp.sqlite --state sync.sqlite …
```

## Before you build on it

- **Run one instance per ERP per retailer.** The sync takes no lock.
- **Stock and prices are never set by hand.** A stock figure is a Stock Entry iVendNext books, never a number the sample sets. A price is written to the price list, never onto a sale.
- **What it does not use.** It reads the feed through the engine transport with today's integration-user grant, which reaches every application's queue; the feed scoped to one application has shipped (the client's `--transport door`, `recipes/event_feed.md` §3) and is not used here. It has no check at payment time; that door has shipped too (`samples/s23_till_guard/`).

## When the sync stops halfway

Restart it. Each write to iVendNext is found again by its own key, so a crash between the write and the cursor does no harm: nothing is lost and nothing is doubled. Each sale arrives once.

## Technical notes

### The tests

| File | What |
|---|---|
| `tests/test_s7.py` | 18 laptop tests, no bench: the sync against an in-memory stand-in and feed |
| *our test bench's own run (not in the kit)* | the bench tests: a full cycle, a crash on the way out and on the way in, a return, a deleted item, three reconciliation canaries; and the money-kit run with the sync running |

### What our test bench's run printed

No screen of ours shows a sync working, so here is the command and what our test bench's run printed (2026-10-07, 29 of 29 checks; the run's own words, trimmed):

```text
== T1 a full cycle: items, prices and stock out; sales in; the books agree
PASS T1 out wrote 4 items, 4 prices and 4 stock entries
PASS T1 a second out writes nothing (the cursor is at the end)
PASS T1 the three sales are in the ERP, once each
PASS T1 the ERP's stock fell by what was sold, and equals the shop's
== T2 the sync stopped mid-batch on the way OUT, restarted: nothing lost, nothing doubled
PASS T2 every ERP movement is in the shop exactly once (8 movements, 8 entries, no key twice)
PASS T2 stock on hand: ERP == shop (10 + 15 − 3 = 22 on both sides)
== T6 the reconciliation can fail — it names what differs, and it never fixes anything
PASS T6 canary: a total that is one unit off is named with both figures
```

### Why this way (R6)

*The 10-line version* (a script that copies every item and sale each night) — rejected: a lost or doubled record is exactly what a large customer cannot afford, and a full copy cannot say which. *A cursor and a key per write* (picked, ~330 lines): each write to iVendNext is found again by its own key, so a crash between the write and the cursor does no harm; each sale arrives once because the feed's seen-set and the ERP's unique invoice number both say so. *A queue service between the two* — rejected: a second thing to run and lose records in.

### Bounds

**One instance per ERP per retailer** — the sync takes no lock (recipe, Bounds). **Not used here, though shipped:** the feed scoped to one application (P-FEED, the client's `--transport door`, `recipes/event_feed.md` §3) — the sync uses the engine transport and the integration user's grant, which reaches every application's queue; a payment-time check (P-CHECK, `samples/s23_till_guard/`). **Never done:** a stock figure is a Stock Entry the engine books, never a number the sample sets; a price is written to the price list, never onto a sale.
