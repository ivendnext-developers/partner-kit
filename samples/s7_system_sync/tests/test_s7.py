"""Laptop tests of S7, no bench: the sync's logic against an in-memory shop and an in-memory event feed.

    python3 -m unittest discover -s samples/s7_system_sync/tests -p 'test_*.py'
"""

import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sync as S  # noqa: E402
from erp import Erp  # noqa: E402

F = S.F


class FakeShop:
    """The Shop's methods, in memory. ``stock`` is only ever changed by a Stock Entry, as in the engine."""
    warehouse = "W"

    def __init__(self):
        self.items, self.prices, self.entries, self.invoices, self.writes = {}, {}, {}, {}, []

    def item(self, code):
        return self.items.get(code)

    def create_item(self, code, name, group):
        self.writes.append(("item", code))
        self.items[code] = {"item_name": name, "item_group": group, "disabled": 0}

    def update_item(self, code, **f):
        self.writes.append(("item", code))
        self.items[code].update(f)

    def item_price(self, code, plist):
        r = self.prices.get((code, plist))
        return {"name": f"{code}/{plist}", "price_list_rate": r} if r is not None else None

    def create_item_price(self, code, plist, rate):
        self.writes.append(("price", code))
        self.prices[(code, plist)] = rate

    def update_item_price(self, name, rate):
        self.writes.append(("price", name))
        code, plist = name.split("/")
        self.prices[(code, plist)] = rate

    def stock_entry_for(self, key):
        return key if key in self.entries else None

    def book_stock(self, key, code, qty, rate):
        self.writes.append(("stock", key))
        self.entries[key] = (code, qty)
        return key

    def bin_qty(self, code):
        q = sum(q for c, q in self.entries.values() if c == code)
        for inv in self.invoices.values():
            if inv["docstatus"] == 1:
                q -= sum(i["qty"] for i in inv["items"] if i["item_code"] == code)
        return float(q)

    def invoice(self, name):
        return self.invoices.get(name)

    def invoices_since(self, since):
        return [dict(i, is_return=i["is_return"]) for i in self.invoices.values() if i["docstatus"] == 1 and i["creation"] >= since]

    def sell(self, name, code, qty, price, day="2026-10-04", ret_against=None):
        sign = -1 if ret_against else 1
        self.invoices[name] = {"name": name, "is_return": 1 if ret_against else 0, "return_against": ret_against, "posting_date": day,
                               "customer": "c", "grand_total": sign * qty * price, "docstatus": 1, "creation": f"{day} 10:00:{len(self.invoices):02d}",
                               "items": [{"item_code": code, "qty": sign * qty, "amount": sign * qty * price}]}


class FakeFeed:
    """A door-shaped feed over a list of events: oldest not-done first."""

    def __init__(self):
        self.rows = []

    def add(self, event, doc):
        self.rows.append({"id": f"e{len(self.rows):03d}", "event": event, "doc_type": "POS Invoice", "doc_name": doc, "raw_event": "x",
                          "at": "t", "done": 0})

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

    def failed(self, id_, note):
        pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.erp = Erp(os.path.join(self.tmp.name, "erp.sqlite"))
        self.store = F.Store(os.path.join(self.tmp.name, "sync.sqlite"))
        S.init_state(self.store.db)
        self.shop, self.feed = FakeShop(), FakeFeed()
        self.erp.add_item("A", "Cable", "Accessories")
        self.erp.set_price("A", "RETAIL", 100.0)
        self.erp.move_stock("A", 20, unit_cost=40.0)

    def tearDown(self):
        self.tmp.cleanup()

    def out(self, **k):
        return S.push_out(self.erp, self.store.db, self.shop, **k)

    def inn(self, **k):
        return F.poll(self.feed, self.store, S.make_handler(self.erp, self.shop), **k)


class OutTests(Base):
    def test_full_cycle_writes_item_price_stock_once(self):
        n = self.out()
        self.assertEqual((n["items"], n["prices"], n["stock_entries"]), (1, 1, 1))
        self.assertEqual(self.shop.items["PP-SYN-A"]["item_name"], "Cable")
        self.assertEqual(self.shop.prices[("PP-SYN-A", "RETAIL")], 100.0)
        self.assertEqual(self.shop.bin_qty("PP-SYN-A"), 20.0)
        self.assertEqual(self.out()["changes"], 0)          # nothing changed since the cursor: nothing is written

    def test_only_what_changed_since_the_cursor(self):
        self.out()
        self.shop.writes.clear()
        self.erp.set_price("A", "RETAIL", 110.0)
        self.out()
        self.assertEqual(self.shop.writes, [("price", "PP-SYN-A/RETAIL")])

    def test_crash_after_the_write_before_the_cursor_nothing_doubled(self):
        self.erp.move_stock("A", 5, unit_cost=40.0)
        self.erp.move_stock("A", 7, unit_cost=40.0)
        with self.assertRaises(SystemExit):
            self.out(crash_after=3)                          # item, price, first movement written; cursor behind by one
        self.out()                                           # restart
        me = self.erp.identity()
        self.assertEqual(sorted(self.shop.entries), [f"PP-SYNC {me} mv:1", f"PP-SYNC {me} mv:2", f"PP-SYNC {me} mv:3"])
        self.assertEqual(self.shop.bin_qty("PP-SYN-A"), 32.0)
        self.assertEqual(len([w for w in self.shop.writes if w[0] == "stock"]), 3)    # each entry written once
        self.assertEqual(self.erp.on_hand("A"), 32.0)

    def test_a_deleted_item_is_disabled_never_deleted(self):
        self.out()
        self.erp.delete_item("A")
        self.out()
        self.assertEqual(self.shop.items["PP-SYN-A"]["disabled"], 1)
        self.assertIn("PP-SYN-A", self.shop.items)

    def test_an_item_added_and_deleted_before_a_pass_does_not_stall_the_ones_after_it(self):
        """The reviewer's scenario: Z added, priced, stocked, deleted — all before the sync ran — then NEXT added."""
        self.out()
        self.erp.add_item("Z", "gone", "G")
        self.erp.set_price("Z", "RETAIL", 5.0)
        self.erp.move_stock("Z", 3, unit_cost=1.0)
        self.erp.delete_item("Z")
        self.erp.add_item("NEXT", "next", "G")
        n = self.out()
        self.assertEqual(n["skipped_deleted"], 2)
        self.assertIsNotNone(self.shop.item("PP-SYN-NEXT"))
        self.assertIsNone(self.shop.item("PP-SYN-Z"))
        self.assertEqual(S.cursor_of(self.store.db), self.erp.db.execute("select max(seq) from changes").fetchone()[0])

    def test_a_price_before_its_item_stops_the_run_and_the_cursor_stays(self):
        self.erp.db.execute("delete from changes where kind='item'")            # a scrambled feed
        with self.assertRaises(RuntimeError):
            self.out()
        self.assertEqual(S.cursor_of(self.store.db), 0)


class TwoSystems(unittest.TestCase):
    def test_a_second_erp_with_the_same_movement_numbers_is_not_mistaken_for_the_first(self):
        """The scar of the first bench run: a rebuilt ERP restarts its movement ids at 1; a key that held only the id found the earlier
        system's entry and wrote no stock at all."""
        with tempfile.TemporaryDirectory() as tmp:
            shop = FakeShop()
            for n in ("one", "two"):
                erp = Erp(os.path.join(tmp, f"{n}.sqlite"))
                db = F.Store(os.path.join(tmp, f"{n}-sync.sqlite")).db
                S.init_state(db)
                erp.add_item(n.upper(), n, "G")
                erp.move_stock(n.upper(), 5, unit_cost=1.0)
                S.push_out(erp, db, shop)
            self.assertEqual(len(shop.entries), 2)
            self.assertEqual((shop.bin_qty("PP-SYN-ONE"), shop.bin_qty("PP-SYN-TWO")), (5.0, 5.0))


class InTests(Base):
    def setUp(self):
        super().setUp()
        self.out()

    def test_sale_arrives_once_even_if_the_event_is_delivered_twice(self):
        self.shop.sell("S1", "PP-SYN-A", 2, 100.0)
        self.feed.add("sale.booked", "S1")
        self.feed.add("sale.booked", "S1")                   # a second delivery under another event id
        n = self.inn()
        self.assertEqual(n["handled"], 2)
        self.assertEqual(self.erp.db.execute("select count(*) from documents").fetchone()[0], 1)
        self.assertEqual(self.erp.on_hand("A"), 18.0)

    def test_crash_mid_batch_then_restart_nothing_lost_nothing_doubled(self):
        for i in range(5):
            self.shop.sell(f"S{i}", "PP-SYN-A", 1, 100.0)
            self.feed.add("sale.booked", f"S{i}")
        with self.assertRaises(SystemExit):
            self.inn(crash_after=3)
        self.assertEqual(self.feed.backlog(), 5)             # nothing was marked done
        n = self.inn()
        self.assertEqual((n["skipped_seen"], n["handled"], n["backlog"]), (3, 2, 0))
        self.assertEqual(self.erp.db.execute("select count(*) from documents").fetchone()[0], 5)
        self.assertEqual(self.erp.on_hand("A"), 15.0)

    def test_a_return_arrives_once_and_links_to_its_sale(self):
        self.shop.sell("S1", "PP-SYN-A", 2, 100.0)
        self.feed.add("sale.booked", "S1")
        self.shop.sell("R1", "PP-SYN-A", 1, 100.0, ret_against="S1")
        self.feed.add("return.booked", "R1")
        self.inn()
        r = self.erp.document_by_shop("R1")
        self.assertEqual(r["kind"], "return")
        self.assertEqual(r["return_of"], self.erp.document_by_shop("S1")["erp_doc_id"])
        self.assertEqual(self.erp.on_hand("A"), 19.0)        # 20 − 2 + 1
        self.feed.add("return.booked", "R1")
        self.inn()
        self.assertEqual(self.erp.db.execute("select count(*) from documents where kind='return'").fetchone()[0], 1)

    def test_a_cancelled_sale_is_no_longer_a_sale(self):
        self.shop.sell("S1", "PP-SYN-A", 2, 100.0)
        self.feed.add("sale.booked", "S1")
        self.inn()
        self.shop.invoices["S1"]["docstatus"] = 2
        self.feed.add("sale.cancelled", "S1")
        self.inn()
        self.assertEqual(self.erp.on_hand("A"), 20.0)

    def test_identity_map_pairs_both_ways(self):
        self.shop.sell("S1", "PP-SYN-A", 1, 100.0)
        self.feed.add("sale.booked", "S1")
        self.inn()
        m = dict(((k, e), s) for k, e, s in self.store.db.execute("select kind, erp_id, shop_name from id_map"))
        self.assertEqual(m[("item", "A")], "PP-SYN-A")
        self.assertEqual(m[("document", self.erp.document_by_shop("S1")["erp_doc_id"])], "S1")


class ReconcileTests(Base):
    def setUp(self):
        super().setUp()
        self.out()
        for i in range(3):
            self.shop.sell(f"S{i}", "PP-SYN-A", 1, 100.0)
            self.feed.add("sale.booked", f"S{i}")
        self.inn()
        self.since = "2026-10-04 00:00:00"

    def rec(self, queued=None):
        return S.reconcile(self.erp, self.store.db, self.shop, self.since, queued)

    def test_clean_when_both_sides_agree(self):
        r = self.rec()
        self.assertTrue(r["clean"], r["differences"])
        self.assertEqual((r["shop_documents"], r["erp_documents"]), (3, 3))

    def test_a_lost_sale_is_named(self):
        self.erp.db.execute("delete from documents where shop_invoice='S1'")
        self.erp.db.execute("delete from lines where erp_doc_id not in (select erp_doc_id from documents)")
        names = [d.get("name") for d in self.rec()["differences"] if d["what"].startswith("booked in the shop")]
        self.assertEqual(names, ["S1"])

    def test_a_wrong_total_is_named_with_both_figures(self):
        self.erp.db.execute("update documents set grand_total=99 where shop_invoice='S2'")
        d = [x for x in self.rec()["differences"] if x["what"] == "total differs"]
        self.assertEqual((d[0]["name"], d[0]["shop_total"], d[0]["erp_total"]), ("S2", 100.0, 99.0))

    def test_stock_that_differs_is_named_and_nothing_is_fixed(self):
        self.shop.entries["by hand"] = ("PP-SYN-A", 4)           # a stock entry made by hand in the shop
        before = (self.erp.on_hand("A"), dict(self.shop.entries))
        d = [x for x in self.rec()["differences"] if x["what"] == "stock on hand differs"]
        self.assertEqual((d[0]["shop"], d[0]["erp"]), (21.0, 17.0))
        self.assertEqual(before, (self.erp.on_hand("A"), dict(self.shop.entries)))   # the report changed nothing

    def test_an_item_the_erp_has_and_the_sync_never_pushed_is_named(self):
        self.erp.add_item("LATE", "late", "G")
        d = [x for x in self.rec()["differences"] if x["what"].startswith("item in the ERP, never pushed")]
        self.assertEqual([x["name"] for x in d], ["PP-SYN-LATE"])

    def test_a_queued_event_is_not_a_difference(self):
        self.shop.sell("S9", "PP-SYN-A", 1, 100.0)
        r = self.rec({"S9"})
        self.assertEqual(r["still_queued"], ["S9"])
        self.assertFalse([d for d in r["differences"] if d.get("name") == "S9"])


if __name__ == "__main__":
    unittest.main()
