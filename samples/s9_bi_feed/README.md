# S9 — a BI feed: sales, lines, payments and returns into a warehouse file, picking up where it stopped

*Start from this sample: copy this folder into `apps/<your app>/` of a repository made from the kit and change the names as this page says; the one-command start does not cover it, because it builds its own manifests ([how](../../recipes/make_it_your_own.md)).*

A small program that copies the retailer's sales, lines, payments and returns into a data warehouse file, and picks up where it stopped. This sample is for a retailer's analytics team that wants the retailer's sales outside the retailer's iVendNext without copying everything every night.

**When to use it:** reports or dashboards outside the retailer's iVendNext need the retailer's sales, kept up to date and checked against the till's own end-of-day figures.

It runs **outside** the retailer's iVendNext, read-only on the business, over the event feed (`recipes/event_feed.md`); written up as a recipe: `recipes/bi_feed.md`.

## What the retailer does

This is for the retailer's analytics team and the retailer's administrator. The retailer's side is two small set-up steps; the rest runs outside the retailer's iVendNext.

1. **Make a user for the feed, read-only on the business.** The administrator makes a user for the feed with a role of its own that can read **POS Invoice** and **POS Closing Entry**, and read and write iVendNext's event log (so the feed can mark events done). It needs nothing else. In that user's **API Access** the administrator presses **Generate Keys** and hands the key and secret to the analytics team ([the integration user recipe](../../recipes/integration_user.md)).
2. **Register the feed in Desk.** The administrator makes a **Registered Application** (this sample calls it `PP BI`): its name, the user from step 1 as the user the feed reads as, and **POS Invoice** ticked on as the record type it follows.
3. **Run the feed outside the retailer's iVendNext.** The analytics team runs `run` with the key (`BI_KEY`, `BI_SECRET`). It copies each sale, return and cancellation into a warehouse file, picking up where it stopped.
4. **Check each day with `control`.** It compares each day's total in the warehouse with the retailer's own end-of-day figure, the **POS Closing Entry**, and names a closing that disagrees.
5. **Heal or restart if needed.** `backfill` catches up if the feed was off or the file lost its last sales; `rebuild` starts a fresh file; `export` writes the CSV files.

**Where it shows.** Nowhere in iVendNext's screens. iVendNext shows only the registration in Desk and the feed's queue. The result is a warehouse file and CSV files on the analytics team's machine, for their own reports and dashboards. Nothing is added to the till, to POS Studio or to a print layout.

**What leaves the retailer's iVendNext.** The retailer's sales: each invoice's header (kind, status, day, customer, totals, tax, discount, till profile), its lines and its payments, and the returns, are read over the API with the feed's key and copied into the warehouse file and the CSV. The feed's key can read iVendNext's event log for **every** application's queue, not only its own; see *Before you copy it*. iVendNext is read, never written, apart from marking the feed's events done.

## The files

| File | What |
|---|---|
| `bi_feed.py` | `run` (the feed, one transaction per invoice together with the seen-set) · `backfill` (by the watermark per record type) · `rebuild` (a full refresh into a fresh file) · `export` (CSV) · `control` (the day's totals beside the POS Closing Entry) |
| `tests/test_s9.py` | 13 laptop tests against an in-memory stand-in and feed |

## How to run it

```bash
BI_KEY=… BI_SECRET=… python3 samples/s9_bi_feed/bi_feed.py control --base https://shop.example --warehouse state/bi.sqlite --since "2026-10-04 00:00:00"
```

1. **`run`**, as often as you like, picks up what is new from the event feed. Each sale is written together with the note that it was handled, so a crash leaves it copied once or not at all.
2. **`control`** checks each day's totals in the warehouse against the retailer's own end-of-day figure (the POS Closing Entry), and names a closing that disagrees.
3. **`backfill`** catches up if the feed was off or the file lost its last sales. **`rebuild`** starts a fresh file.
4. **`export`** writes the warehouse as CSV.

The result is a warehouse file and CSV, not a screen.

## Before you copy it

- **The feed key reaches every application's queue.** The sample reads the feed through the engine transport, whose key sees every application's events. The feed scoped to one application has shipped (the client's `--transport door`, `recipes/event_feed.md` §3); this sample does not use it.

## Technical notes

### Why it is built this way

**Why this way (R6).** *A nightly full dump* — rejected: slow at volume and it cannot say what changed. *Poll by `modified` only* — rejected as the main path: a record committed late behind the cursor is skipped; kept as `backfill`, the second way in. *The feed + one SQLite file for both the warehouse and the seen-set* (picked, ~250 lines): one transaction, so a kill leaves each invoice extracted once or not at all.

**Not used here, though shipped:** the feed scoped to one application (P-FEED, the client's `--transport door`, `recipes/event_feed.md` §3) — this sample uses the engine transport, whose grant reaches every application's queue.

### What was tested

| Where | What |
|---|---|
| `tests/test_s9.py` | 13 laptop tests against an in-memory stand-in and feed |
| *our test bench's own run (not in the kit)* | the bench tests |

What our test bench's run printed (2026-10-07, 23 of 23 checks; trimmed). The result is a warehouse file and CSV, not a screen of ours:

```text
PASS B1 each invoice's header total, every line and every payment equal the shop's own record
PASS B1 exporting again gives the same bytes
PASS B2 the return is a return of that sale, with negative lines
PASS B3 all four are in the warehouse once; their line rows equal the shop's (none lost, none doubled)
PASS B4 after the cancellation the warehouse says cancelled, and the day's revenue excludes it
PASS B5 every POS Closing Entry since the start agrees with the warehouse's total for the invoices it lists (and none is missing)
PASS B5 canary: a total that is one unit off makes the control RED and names the closing
PASS B6 a file missing its last three invoices, with its watermark behind them, is healed by one backfill to equal the full one
```
