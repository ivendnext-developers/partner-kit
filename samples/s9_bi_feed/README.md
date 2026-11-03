# S9 — a BI feed: sales, lines, payments and returns into a warehouse file

A small program that copies the retailer's sales, lines, payments and returns into a data warehouse file, and picks up where it stopped. It reads from the event feed, so nothing is copied twice and a crash leaves each sale copied once or not at all. Each day's total is checked against the till's own end-of-day figure. The result is a warehouse file and CSV files on the analytics team's machine, not a screen.

**Industries:** every industry

**When to use it:** reports or dashboards outside the retailer's iVendNext need the retailer's sales, kept up to date and checked against the till's own end-of-day figures.

## Start from it

**Copy by hand: not an app made here.** Copy `samples/s9_bi_feed/` into your own repository and run `bi_feed.py` on a machine of your own.

## What to change

What a partner usually changes:

- **The warehouse:** the `SCHEMA` and the writes in `bi_feed.py`, if your reports want other columns or another database than the SQLite file.
- **What is exported:** the `export` command's CSV files.
- **The feed's name:** `--app`, the Registered Application the feed follows.
- **The starting day:** `--since` on `control`, `backfill` and `rebuild`.

More: the [recipe](../../recipes/bi_feed.md).

**The customer sets:** a user for the feed with a role of its own that can read POS Invoice and POS Closing Entry, and read and write the event log ([integration user](../../recipes/integration_user.md)); and a Registered Application (this sample calls it `PP BI`) that names that user and follows POS Invoice.

## Run it

```bash
BI_KEY=… BI_SECRET=… python3 samples/s9_bi_feed/bi_feed.py control --base https://shop.example --warehouse state/bi.sqlite --since "2026-10-04 00:00:00"
python3 -m unittest discover -s samples/s9_bi_feed/tests -p 'test_*.py'
```

`run` picks up what is new, `backfill` catches up after a gap, `rebuild` starts a fresh file, `export` writes the CSV files and `control` names a day that disagrees with the till's closing.

## Versions

### 1.0.0

- First version in the kit: sales, lines, payments and returns into a warehouse file, picking up where it stopped.
- The set-up steps say the install makes the app's own user (POS 2.1.0.667 or later).
