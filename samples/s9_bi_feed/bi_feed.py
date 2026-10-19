#!/usr/bin/env python3
"""S9 — an incremental BI feed: sales, lines, payments and returns into a warehouse file. Python 3.9+, stdlib only.

    BI_KEY=… BI_SECRET=… python3 bi_feed.py run --base https://shop.example --app "PP BI" --warehouse state/bi.sqlite --watch 30
    python3 bi_feed.py export  --warehouse state/bi.sqlite --out state/csv
    python3 bi_feed.py control --base … --warehouse state/bi.sqlite --since "2026-10-04 00:00:00"

How it picks up exactly where it stopped:
  RUN       reads the event feed (``tools/feed_client``, recipes/event_feed.md): a sale booked, a return booked, a sale cancelled
            each name an invoice; the invoice is read over the API (with its lines and payments) and replaces its rows in the
            warehouse. The seen-set and the warehouse live in the SAME SQLite file and are written in ONE transaction, so a
            kill at any moment leaves each invoice extracted once or not at all — and the feed hands back what was not done.
  BACKFILL  the second way in, independent of the feed: per record type (sale, return) the WATERMARK is the latest ``modified``
            time extracted; backfill reads the invoices modified at or after it. Use it after the feed was off, or to heal.
  PAGES     backfill and rebuild read invoices a page at a time — three list calls per page (headers; every line through
            ``items.<field>``; every payment through ``payments.<field>``), never one call per invoice (recipes/bulk_reads.md).
  REBUILD   a full refresh into a fresh file: every invoice created since a date. A rebuilt file and an incremental one agree
            (the tests compare them row by row).
  EXPORT    the warehouse as CSV files (sales, lines, payments, control), the same every time for the same data.
  CONTROL   the day's control totals from the warehouse beside the shop's own report for the day: the POS Closing Entry (each
            closing's grand total and the invoices it lists). A day that does not agree is named; an invoice booked in a day
            that is not closed yet is listed apart (after the shop is asked that it still has it booked), not as a difference.
A cancelled sale stays in the warehouse as ``cancelled`` and is never revenue.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import feed_client as F  # noqa: E402

SCHEMA = """
create table if not exists fact_sale (invoice text primary key, kind text not null, status text not null, posting_date text, customer text,
    grand_total real, net_total real, tax_total real, discount real, pos_profile text, return_against text, creation text, modified text,
    extracted_at text default (datetime('now')));
create table if not exists fact_line (invoice text, idx integer, item_code text, qty real, rate real, amount real, primary key (invoice, idx));
create table if not exists fact_payment (invoice text, idx integer, mode text, amount real, primary key (invoice, idx));
create table if not exists watermark (record_type text primary key, last_modified text, records integer not null default 0);
"""
FIELDS = ["name", "docstatus", "is_return", "return_against", "posting_date", "customer", "grand_total", "net_total", "total_taxes_and_charges",
          "discount_amount", "pos_profile", "creation", "modified"]
WANT = ("sale.booked", "return.booked", "sale.cancelled")


def init(db):
    db.executescript(SCHEMA)


def upsert(db, doc) -> str | None:
    """Replace one invoice's rows (header, lines, payments) and move its record type's watermark. A draft is not extracted."""
    if doc["docstatus"] not in (1, 2):
        return None
    kind = "return" if doc.get("is_return") else "sale"
    name = doc["name"]
    db.execute("delete from fact_line where invoice=?", (name,))
    db.execute("delete from fact_payment where invoice=?", (name,))
    db.execute("insert or replace into fact_sale (invoice, kind, status, posting_date, customer, grand_total, net_total, tax_total, discount, "
               "pos_profile, return_against, creation, modified) values (?,?,?,?,?,?,?,?,?,?,?,?,?)",
               (name, kind, "cancelled" if doc["docstatus"] == 2 else "booked", doc["posting_date"], doc.get("customer"), float(doc["grand_total"]),
                float(doc.get("net_total") or 0), float(doc.get("total_taxes_and_charges") or 0), float(doc.get("discount_amount") or 0),
                doc.get("pos_profile"), doc.get("return_against"), doc["creation"], doc["modified"]))
    for i, ln in enumerate(doc.get("items") or []):
        db.execute("insert into fact_line values (?,?,?,?,?,?)", (name, i, ln["item_code"], float(ln["qty"]), float(ln["rate"]), float(ln["amount"])))
    for i, p in enumerate(doc.get("payments") or []):
        db.execute("insert into fact_payment values (?,?,?,?)", (name, i, p["mode_of_payment"], float(p["amount"])))
    db.execute("insert into watermark (record_type, last_modified, records) values (?,?,0) on conflict(record_type) do update set "
               "last_modified=max(last_modified, excluded.last_modified)", (kind, doc["modified"]))
    return kind


def read_invoice(api: F.Api, name: str):
    try:
        return api.call("GET", f"/api/resource/POS%20Invoice/{urllib.parse.quote(name)}").get("data")
    except F.FeedError as e:
        if str(e).startswith("404"):
            return None
        raise


PAGE = 200
LINE_FIELDS = ["name", "items.idx as line_idx", "items.item_code as item_code", "items.qty as qty", "items.rate as rate", "items.amount as amount"]
PAY_FIELDS = ["name", "payments.idx as line_idx", "payments.mode_of_payment as mode_of_payment", "payments.amount as amount"]


def read_invoices(api: F.Api, names):
    """The invoices ``names`` with their lines and payments, in three list calls: a list call may name a child table's fields
    (``items.qty``) and returns one row per child row, the header's ``name`` on each (recipes/bulk_reads.md)."""
    if not names:
        return []
    def rows(fields):
        return api.call("GET", "/api/resource/POS%20Invoice", {"filters": json.dumps([["name", "in", names]]), "fields": json.dumps(fields),
                                                             "limit_page_length": 0}).get("data", [])
    docs = {d["name"]: dict(d, items=[], payments=[]) for d in rows(FIELDS)}
    for key, fields in (("items", LINE_FIELDS), ("payments", PAY_FIELDS)):
        for r in sorted(rows(fields), key=lambda r: (r["name"], r.get("line_idx") or 0)):
            if r["name"] in docs and r.get("line_idx") is not None:   # an invoice with no row of this kind comes back once, empty
                docs[r["name"]][key].append({k: v for k, v in r.items() if k not in ("name", "line_idx")})
    return [docs[n] for n in names if n in docs]


def pages(seq, size=None):
    size = size or PAGE
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def make_handler(api: F.Api):
    def handler(ev, db):
        if ev["event"] not in WANT:
            return
        doc = read_invoice(api, ev["doc_name"])
        if doc is None:
            raise RuntimeError(f"{ev['doc_name']} cannot be read")
        upsert(db, doc)
    return handler


def _names(api, filters, order="modified asc"):
    return api.call("GET", "/api/resource/POS%20Invoice", {"filters": json.dumps(filters), "fields": json.dumps(["name", "modified", "is_return"]),
                                                          "order_by": order, "limit_page_length": 0}).get("data", [])


def rebuild(api: F.Api, db, since: str) -> int:
    """A full refresh: every invoice created since ``since``, replacing whatever is in the file."""
    db.execute("begin")
    try:
        for t in ("fact_sale", "fact_line", "fact_payment", "watermark"):
            db.execute(f"delete from {t}")
        n = 0
        for page in pages([r["name"] for r in _names(api, [["docstatus", "in", [1, 2]], ["creation", ">=", since]])]):
            for doc in read_invoices(api, page):
                upsert(db, doc)
                n += 1
        db.execute("commit")
        return n
    except BaseException:
        db.execute("rollback")
        raise


def backfill(api: F.Api, db) -> dict:
    """Per record type, the invoices modified at or after its watermark (equal times are read again; an upsert is harmless twice)."""
    out = {}
    for kind, is_return in (("sale", 0), ("return", 1)):
        row = db.execute("select last_modified from watermark where record_type=?", (kind,)).fetchone()
        flt = [["docstatus", "in", [1, 2]], ["is_return", "=", is_return]] + ([["modified", ">=", row[0]]] if row else [])
        n = 0
        for page in pages([r["name"] for r in _names(api, flt)]):
            docs = read_invoices(api, page)
            db.execute("begin")
            try:
                for doc in docs:
                    upsert(db, doc)
                db.execute("commit")
            except BaseException:
                db.execute("rollback")
                raise
            n += len(docs)
        out[kind] = n
    return out


def export(db, out_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    counts = {}
    for name, sql in (("sales", "select * from fact_sale order by invoice"), ("lines", "select * from fact_line order by invoice, idx"),
                      ("payments", "select * from fact_payment order by invoice, idx"),
                      ("control", "select posting_date, sum(kind='sale' and status='booked'), round(sum(case when kind='sale' and status='booked' then grand_total else 0 end),2), "
                                  "sum(kind='return' and status='booked'), round(sum(case when kind='return' and status='booked' then grand_total else 0 end),2), "
                                  "sum(status='cancelled') from fact_sale group by posting_date order by posting_date")):
        cur = db.execute(sql)
        with open(os.path.join(out_dir, f"{name}.csv"), "w", newline="") as f:
            w = csv.writer(f)
            w.writerow([d[0] if name != "control" else h for d, h in zip(cur.description, ("posting_date", "sales", "sales_total", "returns", "returns_total", "cancelled"))])
            rows = cur.fetchall()
            w.writerows(rows)
        counts[name] = len(rows)
    return counts


def control(api: F.Api, db, since: str) -> dict:
    """The warehouse's day totals beside the shop's own report: POS Closing Entry (its grand total and the invoices it lists)."""
    days = {}
    for day, kind, status, n, tot in db.execute("select posting_date, kind, status, count(*), round(sum(grand_total),2) from fact_sale "
                                                "where creation >= ? group by 1,2,3", (since,)):
        d = days.setdefault(day, {"sales": 0, "sales_total": 0.0, "returns": 0, "returns_total": 0.0, "cancelled": 0})
        if status == "cancelled":
            d["cancelled"] += n
        else:
            d["sales" if kind == "sale" else "returns"] += n
            d["sales_total" if kind == "sale" else "returns_total"] = tot
    diffs, closings, listed = [], [], set()
    for c in api.call("GET", "/api/resource/POS%20Closing%20Entry", {
            "filters": json.dumps([["docstatus", "=", 1], ["creation", ">=", since]]), "fields": json.dumps(["name", "posting_date", "grand_total"]),
            "limit_page_length": 0}).get("data", []):
        doc = api.call("GET", f"/api/resource/POS%20Closing%20Entry/{urllib.parse.quote(c['name'])}").get("data")
        inv = [t["pos_invoice"] for t in doc.get("pos_transactions") or []]
        listed |= set(inv)
        have = {r[0]: r[1] for r in db.execute(f"select invoice, grand_total from fact_sale where status='booked' and invoice in ({','.join('?' * len(inv)) or 'null'})", inv)}
        mine = round(sum(have.values()), 2)
        row = {"closing": c["name"], "posting_date": c["posting_date"], "shop_total": round(float(c["grand_total"]), 2), "warehouse_total": mine,
               "invoices": len(inv), "in_warehouse": len(have)}
        closings.append(row)
        if len(have) != len(inv):
            diffs.append(dict(row, what="the closing lists invoices the warehouse does not hold as booked", missing=sorted(set(inv) - set(have))))
        elif abs(mine - row["shop_total"]) > 0.005:
            diffs.append(dict(row, what="the closing's grand total differs from the warehouse's total for its invoices"))
    open_day = []
    for (name,) in db.execute("select invoice from fact_sale where status='booked' and creation >= ? order by invoice", (since,)).fetchall():
        if name in listed:
            continue
        doc = read_invoice(api, name)       # no closing lists it: it is in an open day only if the shop STILL has it booked
        if doc is None or doc["docstatus"] != 1:
            diffs.append({"what": "booked in the warehouse, but the shop has it cancelled or gone and no closing lists it", "invoice": name,
                          "shop_docstatus": None if doc is None else doc["docstatus"]})
        else:
            open_day.append(name)
    return {"since": since, "days": days, "closings": closings, "differences": diffs, "in_an_open_day": open_day, "clean": not diffs}


def main(argv=None):
    p = argparse.ArgumentParser(description="S9 — an incremental BI feed")
    p.add_argument("command", choices=("run", "backfill", "rebuild", "export", "control", "status"))
    p.add_argument("--base")
    p.add_argument("--app", help="the Registered Application's name (engine transport)")
    p.add_argument("--warehouse", default="state/bi.sqlite")
    p.add_argument("--out", default="state/csv")
    p.add_argument("--since")
    p.add_argument("--crash-after", type=int, help="test only: exit after handling N events, before marking them done")
    p.add_argument("--watch", type=float)
    a = p.parse_args(argv)
    store = F.Store(a.warehouse)
    init(store.db)
    if a.command == "export":
        print(json.dumps(export(store.db, a.out)))
        return
    if a.command == "status":
        print(json.dumps({"invoices": store.db.execute("select count(*) from fact_sale").fetchone()[0],
                          "watermark": {r[0]: r[1] for r in store.db.execute("select record_type, last_modified from watermark")},
                          "events_seen": store.db.execute("select count(*) from seen").fetchone()[0]}))
        return
    key, secret = os.environ.get("BI_KEY"), os.environ.get("BI_SECRET")
    if not (key and secret and a.base):
        sys.exit("set BI_KEY and BI_SECRET in the environment and give --base")
    api = F.Api(a.base, key, secret)
    if a.command == "rebuild":
        print(json.dumps({"rebuilt": rebuild(api, store.db, a.since or sys.exit("--since is required"))}))
    elif a.command == "backfill":
        print(json.dumps(backfill(api, store.db)))
    elif a.command == "control":
        print(json.dumps(control(api, store.db, a.since or sys.exit("--since is required")), default=str))
    else:
        if not a.app:
            sys.exit("--app is required")
        feed = F.EngineFeed(api, a.app)
        while True:
            print(json.dumps(F.poll(feed, store, make_handler(api), crash_after=a.crash_after)), flush=True)
            if not a.watch:
                break
            time.sleep(a.watch)


if __name__ == "__main__":
    try:
        main()
    except (F.FeedError, RuntimeError) as e:
        sys.exit(f"BI_ERROR {e}")
