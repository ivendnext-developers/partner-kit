"""Laptop tests of S9, no bench: the extractor against an in-memory shop (record API) and an in-memory event feed.

    python3 -m unittest discover -s samples/s9_bi_feed/tests -p 'test_*.py'
"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bi_feed as B  # noqa: E402

F = B.F


class FakeApi:
    def __init__(self):
        self.invoices, self.closings = {}, {}
        self.calls = []   # (kind, path) per call: "one" = a single-record read, "list" = a list call

    def add(self, name, total, day="2026-10-04", ret=0, status=1, items=None, mod=None, against=None):
        self.invoices[name] = {"name": name, "docstatus": status, "is_return": ret, "return_against": against, "posting_date": day, "customer": "c",
                               "grand_total": total, "net_total": total, "total_taxes_and_charges": 0, "discount_amount": 0, "pos_profile": "P",
                               "creation": f"{day} 09:00:{len(self.invoices):02d}", "modified": mod or f"{day} 09:30:{len(self.invoices):02d}",
                               "items": items or [{"item_code": "I", "qty": -1 if ret else 1, "rate": abs(total), "amount": total}],
                               "payments": [{"mode_of_payment": "Cash", "amount": total}]}

    def close(self, name, names, day="2026-10-04"):
        self.closings[name] = {"name": name, "posting_date": day, "creation": f"{day} 20:00:00",
                               "grand_total": round(sum(self.invoices[n]["grand_total"] for n in names), 2),
                               "pos_transactions": [{"pos_invoice": n} for n in names]}

    def call(self, method, path, params=None, body=None):
        p = urllib.parse.unquote(path)
        if p == "/api/resource/POS Invoice":
            self.calls.append(("list", p))
            rows = []
            for d in self.invoices.values():
                ok = True
                for f, op, v in json.loads(params["filters"]):
                    val = d[f]
                    ok &= {"in": lambda: val in v, "=": lambda: val == v, ">=": lambda: val >= v}[op]()
                if ok:
                    rows.append(dict(d))
            rows = sorted(rows, key=lambda r: (r["modified"], r["name"]))
            fields = json.loads(params.get("fields") or "[]")
            child = {f.split(".")[0] for f in fields if "." in f}
            if child:   # the API's join: one row per child row, the header's name on each; aliases name the keys
                (table,) = child
                out = []
                for d in rows:
                    for i, c in enumerate(d[table], 1):
                        r = {"name": d["name"]}
                        for f in fields:
                            if "." in f:
                                src, alias = f.split(".", 1)[1].split(" as ")
                                r[alias] = i if src == "idx" else c[src]
                        out.append(r)
                return {"data": out}
            return {"data": rows}
        if p.startswith("/api/resource/POS Invoice/"):
            self.calls.append(("one", p))
            n = p.rsplit("/", 1)[1]
            if n not in self.invoices:
                raise F.FeedError("404 not found")
            return {"data": json.loads(json.dumps(self.invoices[n]))}
        if p == "/api/resource/POS Closing Entry":
            return {"data": [dict(c) for c in self.closings.values()]}
        if p.startswith("/api/resource/POS Closing Entry/"):
            return {"data": self.closings[p.rsplit("/", 1)[1]]}
        raise AssertionError(p)


class FakeFeed:
    def __init__(self):
        self.rows = []

    def add(self, event, doc):
        self.rows.append({"id": f"e{len(self.rows):03d}", "event": event, "doc_type": "POS Invoice", "doc_name": doc, "raw_event": "x", "at": "t", "done": 0})

    def events(self, limit=100, page=None):
        todo = [r for r in self.rows if not r["done"]]
        return [dict(r) for r in todo[:limit]], (str(limit) if len(todo) > limit else None), len(todo)

    def backlog(self):
        return sum(1 for r in self.rows if not r["done"])

    def done(self, ids):
        for r in self.rows:
            if r["id"] in ids:
                r["done"] = 1
        return len(ids)

    def failed(self, *a):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = F.Store(os.path.join(self.tmp.name, "bi.sqlite"))
        B.init(self.store.db)
        self.api, self.feed = FakeApi(), FakeFeed()

    def tearDown(self):
        self.tmp.cleanup()

    def sale(self, name, total, **k):
        self.api.add(name, total, **k)
        self.feed.add("return.booked" if k.get("ret") else "sale.booked", name)

    def run_(self, **k):
        return F.poll(self.feed, self.store, B.make_handler(self.api), **k)

    def facts(self, db=None):
        db = db or self.store.db
        return [db.execute(f"select * from {t} order by 1,2").fetchall() for t in ("fact_sale", "fact_line", "fact_payment")]


class Extract(Base):
    def test_header_lines_payments_extracted(self):
        self.sale("S1", 100.0, items=[{"item_code": "A", "qty": 1, "rate": 40, "amount": 40}, {"item_code": "B", "qty": 1, "rate": 60, "amount": 60}])
        self.run_()
        self.assertEqual(self.store.db.execute("select invoice, kind, status, grand_total from fact_sale").fetchall(), [("S1", "sale", "booked", 100.0)])
        self.assertEqual(self.store.db.execute("select item_code, amount from fact_line order by idx").fetchall(), [("A", 40.0), ("B", 60.0)])
        self.assertEqual(self.store.db.execute("select mode, amount from fact_payment").fetchall(), [("Cash", 100.0)])

    def test_a_return_is_a_return(self):
        self.sale("S1", 100.0)
        self.sale("R1", -100.0, ret=1, against="S1")
        self.run_()
        self.assertEqual(self.store.db.execute("select kind, return_against from fact_sale where invoice='R1'").fetchone(), ("return", "S1"))

    def test_only_new_events_touch_rows(self):
        self.sale("S1", 100.0)
        self.run_()
        self.store.db.execute("update fact_sale set extracted_at='old'")
        self.sale("S2", 50.0)
        self.run_()
        self.assertEqual(self.store.db.execute("select extracted_at from fact_sale where invoice='S1'").fetchone()[0], "old")
        self.assertEqual(self.run_()["handled"], 0)

    def test_crash_mid_extract_restart_each_invoice_once(self):
        for i in range(5):
            self.sale(f"S{i}", 10.0 + i)
        with self.assertRaises(SystemExit):
            self.run_(crash_after=3)
        self.assertEqual(self.feed.backlog(), 5)
        n = self.run_()
        self.assertEqual((n["skipped_seen"], n["handled"], n["backlog"]), (3, 2, 0))
        self.assertEqual(self.store.db.execute("select count(*), count(distinct invoice) from fact_sale").fetchone(), (5, 5))
        self.assertEqual(self.store.db.execute("select count(*) from fact_line").fetchone()[0], 5)

    def test_a_cancelled_sale_is_cancelled_not_revenue(self):
        self.sale("S1", 100.0)
        self.sale("S2", 40.0)
        self.run_()
        self.api.invoices["S1"]["docstatus"] = 2
        self.api.invoices["S1"]["modified"] = "2026-10-04 12:00:00"
        self.feed.add("sale.cancelled", "S1")
        self.run_()
        self.assertEqual(self.store.db.execute("select status from fact_sale where invoice='S1'").fetchone()[0], "cancelled")
        out = self.api.closings
        self.api.close("C1", ["S2"])
        c = B.control(self.api, self.store.db, "2026-10-04 00:00:00")
        self.assertTrue(c["clean"], c)
        self.assertEqual(c["days"]["2026-10-04"]["sales_total"], 40.0)
        self.assertEqual(c["days"]["2026-10-04"]["cancelled"], 1)

    def test_an_event_that_is_not_ours_writes_nothing(self):
        self.api.add("S1", 1.0)
        self.feed.add("pos_invoice.on_update", "S1")
        self.run_()
        self.assertEqual(self.store.db.execute("select count(*) from fact_sale").fetchone()[0], 0)


class Warehouse(Base):
    def setUp(self):
        super().setUp()
        for i in range(4):
            self.sale(f"S{i}", 10.0 * (i + 1))
        self.run_()

    def test_rebuild_equals_incremental(self):
        other = F.Store(os.path.join(self.tmp.name, "rebuilt.sqlite"))
        B.init(other.db)
        B.rebuild(self.api, other.db, "2026-10-04 00:00:00")
        strip = lambda rows: [r[:-1] if len(r) == 14 else r for r in rows]  # noqa: E731 (extracted_at is the last column of fact_sale)
        a, b = self.facts(), self.facts(other.db)
        self.assertEqual((strip(a[0]), a[1], a[2]), (strip(b[0]), b[1], b[2]))
        self.assertEqual(self.store.db.execute("select * from watermark order by 1").fetchall(), other.db.execute("select * from watermark order by 1").fetchall())

    def test_rebuild_reads_pages_not_one_call_per_invoice(self):
        other = F.Store(os.path.join(self.tmp.name, "paged.sqlite"))
        B.init(other.db)
        for i in range(4, 9):   # a second page at PAGE=4
            self.sale(f"S{i}", 1.0 * i, items=[{"item_code": "A", "qty": 1, "rate": 1.0, "amount": 1.0},
                                                {"item_code": "B", "qty": 2, "rate": i - 0.5, "amount": 2 * i - 1.0}])
        self.api.calls.clear()
        page, B.PAGE = B.PAGE, 4
        try:
            B.rebuild(self.api, other.db, "2026-10-04 00:00:00")
        finally:
            B.PAGE = page
        self.assertEqual([k for k, _ in self.api.calls if k == "one"], [])
        self.assertEqual(len(self.api.calls), 1 + 3 * 3)   # the names, then three calls for each of three pages
        self.assertEqual(other.db.execute("select count(*) from fact_line").fetchone()[0], 4 + 5 * 2)
        self.assertEqual(other.db.execute("select item_code, qty, amount from fact_line where invoice='S6' order by idx").fetchall(),
                         [("A", 1.0, 1.0), ("B", 2.0, 11.0)])

    def test_backfill_heals_a_gap_behind_the_watermark(self):
        full = self.facts()
        last = self.store.db.execute("select invoice from fact_sale order by modified desc limit 2").fetchall()
        older = self.store.db.execute("select max(modified) from fact_sale where invoice not in (?,?)", [r[0] for r in last]).fetchone()[0]
        for r in last:
            for t in ("fact_sale", "fact_line", "fact_payment"):
                self.store.db.execute(f"delete from {t} where invoice=?", (r[0],))
        self.store.db.execute("update watermark set last_modified=?", (older,))
        B.backfill(self.api, self.store.db)
        got = self.facts()
        self.assertEqual([[r[:-1] if t == 0 else r for r in rows] for t, rows in enumerate(got)], [[r[:-1] if t == 0 else r for r in rows] for t, rows in enumerate(full)])

    def test_control_clean_then_names_a_total_and_a_missing_invoice(self):
        self.api.close("C1", ["S0", "S1"])
        self.api.close("C2", ["S2", "S3"])
        since = "2026-10-04 00:00:00"
        self.assertTrue(B.control(self.api, self.store.db, since)["clean"])
        self.store.db.execute("update fact_sale set grand_total=grand_total+1 where invoice='S2'")
        d = B.control(self.api, self.store.db, since)["differences"]
        self.assertEqual([(x["closing"], x["what"][:20]) for x in d], [("C2", "the closing's grand ")])
        self.store.db.execute("delete from fact_sale where invoice='S0'")
        d = B.control(self.api, self.store.db, since)["differences"]
        self.assertIn("S0", [m for x in d for m in x.get("missing", [])])

    def test_unclosed_invoices_are_listed_apart(self):
        self.api.close("C1", ["S0", "S1", "S2"])
        c = B.control(self.api, self.store.db, "2026-10-04 00:00:00")
        self.assertEqual((c["clean"], c["in_an_open_day"]), (True, ["S3"]))

    def test_an_unlisted_invoice_the_shop_has_cancelled_is_a_difference_not_an_open_day(self):
        """A cancel event that never arrived: the warehouse still holds S1 as booked; the day closed without it."""
        self.api.invoices["S1"]["docstatus"] = 2
        self.api.close("C1", ["S0", "S2", "S3"])
        c = B.control(self.api, self.store.db, "2026-10-04 00:00:00")
        self.assertFalse(c["clean"])
        self.assertEqual([(d["invoice"], d["shop_docstatus"]) for d in c["differences"]], [("S1", 2)])
        self.assertEqual(c["in_an_open_day"], [])

    def test_export_is_deterministic_and_complete(self):
        out = os.path.join(self.tmp.name, "csv")
        n = B.export(self.store.db, out)
        first = open(os.path.join(out, "sales.csv"), "rb").read()
        B.export(self.store.db, out)
        self.assertEqual(first, open(os.path.join(out, "sales.csv"), "rb").read())
        self.assertEqual((n["sales"], n["lines"], n["payments"]), (4, 4, 4))


if __name__ == "__main__":
    unittest.main()
