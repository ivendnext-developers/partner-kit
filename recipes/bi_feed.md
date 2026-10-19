# Feed a data warehouse from the shop — the incremental BI-feed recipe

This recipe copies the shop's **sales, lines, payments and returns** into a data warehouse. It copies **only what is new**, never misses a record the shop wrote while the feed was down, and **agrees with the shop's own day-end report**. It is for a retailer's analytics team. **Reference implementation:** `samples/s9_bi_feed/bi_feed.py` (Python, standard library only; SQLite and CSV as the warehouse — the same logic loads any database). It is built on the event-feed client (`tools/feed_client/`, `recipes/event_feed.md`).

**When to use it.** When reports or dashboards outside the shop need the shop's sales, kept up to date without a full copy every night.

## What it keeps

- `fact_sale`: one row per POS Invoice — kind *sale* or *return*, status *booked* or *cancelled*, day, customer, grand total, net, tax, discount, profile, the sale a return is against, creation and modified times.
- `fact_line` and `fact_payment`.
- A **watermark per record type** (sale, return: the latest `modified` extracted).
- The feed's **seen-set**: the events already handled.

The feed's key is **read-only on the business**: the log (to mark events done), and read on POS Invoice and POS Closing Entry.

## Steps

1. **Give the feed its key**, read-only on the business as above, and set it as `BI_KEY` and `BI_SECRET`.
2. **Run `run` as often as you like.** It picks up what is new from the event feed (below).
3. **Check each day against the shop with `control`** (below).
4. **If the feed was off, or the file lost its tail, run `backfill`.** To start a fresh file, run `rebuild`.
5. **Hand the warehouse on with `export`** (CSV).

## Four ways in, one result

| Command | How it picks up |
|---|---|
| **`run`** | the event feed: a sale booked, a return booked or a sale cancelled names an invoice; the invoice is **read over the API** (header, lines, payments) and **replaces its rows**. The seen-set and the warehouse are **in the same SQLite file and written in one transaction**, so a kill at any moment leaves each invoice extracted once or not at all, and the feed hands back what was not marked done |
| **`backfill`** | independent of the feed: per record type, the invoices **modified at or after its watermark**. For when the feed was off, or to heal a gap at the end of the file. An upsert is harmless twice, so equal times are read again |
| **`rebuild`** | a full refresh into a fresh file: every invoice created since a date |
| **`export`** | the warehouse as CSV (`sales`, `lines`, `payments`, `control`) — the same bytes for the same data |

## The control total — the day agrees with the shop's own report

```bash
BI_KEY=… BI_SECRET=… python3 samples/s9_bi_feed/bi_feed.py control --base … --warehouse state/bi.sqlite --since "2026-10-04 00:00:00"
```

The shop's own report for a day is the **POS Closing Entry**: the till's own end-of-day figure.
- For each closing, the warehouse adds up the **booked** invoices the closing lists and compares the sum with the closing's grand total. It also names a closing that lists an invoice the warehouse does not hold as booked.
- An invoice that **no closing lists** is listed apart (`in_an_open_day`) only after the shop is asked and still has it **booked**. If the shop has it cancelled or gone (a cancel event that never arrived), it is a **difference**. Otherwise the warehouse would call revenue the shop no longer has.
- A **cancelled** sale stays in the warehouse as `cancelled` and is **never revenue**. The day's revenue excludes it, and the closing built after the cancellation does not list it.

## When the feed is down, and when the till is offline

- **The feed or your job stops:** nothing is lost. The feed hands back everything not marked done, and a kill leaves each invoice extracted once or not at all.
- **The file lost its tail, or starts from a date the feed never saw:** run `backfill`.
- **The shop is busy:** events can lag the sale by a minute when the shop's one background worker is busy.
- **The till is offline:** offline sales arrive late, when the till is back.

## Limits to know before you build

- **Rows are as of extraction.** The feed follows a sale booked, a return booked and a sale cancelled. **Any other later change to a booked invoice is not followed.** `backfill` re-reads by `modified` if you need other changes.
- `backfill` moves forward from the watermark only. **A row deleted from the middle of the file is not re-read** — rebuild.
- **The feed grant cannot be scoped to one application today** (`recipes/event_feed.md` §3).
- The one-transaction guarantee needs the seen-set and the facts in the **same** database.
- Drafts are not extracted. Payments are the invoice's payment rows (change given is not netted). Other record types (Stock Entry, Customer) are the same pattern with another handler.

## Technical notes

**Proven** on our test bench. The bench holds POS Closing Entries, and also back-office Sales Invoices merged from them; the closing is the till's own end-of-day figure.

### What the kit has proven (23 checks)
- **Extract:** three sales — each header total, every line and every payment equals the shop's own record (read back with the BI key); a two-line basket extracted both lines; the CSV files have one row per record (counts compared, not every value); exporting twice gives the same bytes.
- **Incremental:** four more invoices (two sales, a sale and its return) — the warehouse holds the old three and exactly those four; **the first three rows were not touched** (same extraction time); the return is a return of that sale with negative lines; a second run handles nothing.
- **Killed mid-extract:** crashed after 8 handled events, restarted — four invoices once each; line rows equal the shop's (none lost, none doubled); the seen-set holds each event once.
- **Cancelled:** while its day is open the sale is booked and listed as in an open day; after the cancellation (and the day's close) it reads `cancelled` and the day's revenue, added up from the shop's own totals of the invoices the warehouse lists as booked, excludes it (the independent check of the day is the closing control below).
- **Control:** every POS Closing Entry since the start agrees (5 closings); canaries — a total one unit off turns it RED and names the closing; an invoice deleted from the warehouse turns it RED and names the invoice; the file put back, GREEN.
- **A rebuild equals the incremental file** row for row (sales, lines, payments, watermarks); **a file missing its last three invoices, with its watermark behind them, is healed by one `backfill`** to equal the full one.

### Bounds, stated
- **Rows are as of extraction.** The handler follows a sale booked, a return booked and a sale cancelled; **any other later change to a booked invoice is not followed** (the feed names it, the handler ignores it). Measured: after every test day had closed, a full rebuild equalled the incremental file row for row (including each invoice's `modified`), so the day's close changed nothing the warehouse holds. `backfill` re-reads by `modified` if you need other changes.
- `backfill` moves forward from the watermark only: **a row deleted from the middle of the file is not re-read** — rebuild.
- **The feed grant cannot be scoped to one application today** (`recipes/event_feed.md` §3); events can lag the sale by a minute when the shop's one background worker is busy; offline sales arrive late.
- `backfill` is the watermark's use, not a second path for a queue: the feed already hands back everything not marked done. It is for a file that lost its tail, or one started from a date the feed never saw.
- Volume: tens of invoices on the bench; one invoice read per event. `backfill` and `rebuild` read a page at a time (three list calls per page, `recipes/bulk_reads.md`; tested against a stand-in shop, not yet on the bench). SQLite stands in for a warehouse database; the one-transaction guarantee needs the seen-set and the facts in the **same** database.
- Drafts are not extracted; payments are the invoice's payment rows (change given is not netted); other record types (Stock Entry, Customer) are the same pattern with another handler.
