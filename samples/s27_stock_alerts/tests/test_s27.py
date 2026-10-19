"""Laptop tests of S27, no shop: the rules, and the service against an in-memory shop.

    python3 -m unittest discover -s samples/s27_stock_alerts/tests -p 'test_*.py'
"""

import datetime as dt
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import alerts as A  # noqa: E402
import run as R  # noqa: E402

TODAY = dt.date(2026, 10, 16)
HQ, S1, S2, CLR = "Head Office", "Store 1", "Store 2", "Clearance"


class FakeShop:
    """Stock, reorder rows, batches, requests and alerts in memory. Like the shop, it lists only draft requests; unlike
    the shop it does NOT refuse a second alert with the same name, so the service's own check is what is tested."""

    def __init__(self, **settings):
        self.st = {"name": "Default", "enabled": 1, "source_warehouse": HQ, "expiry_days": 20, "stores": [], **settings}
        self.whs = [{"name": n, "is_group": 0, "disabled": 0, "company": "Shop"} for n in (HQ, S1, S2, CLR)]
        self.whs.append({"name": "All", "is_group": 1, "disabled": 0, "company": "Shop"})
        self.rows, self.bin, self.batch, self.stock = [], {}, [], {}
        self.mr, self.alerts, self.writes, self.n = {}, [], [], 0
        self.fail_alerts = 0

    # the test's own hands
    def reorder(self, item, store, level, qty, kind="Transfer"):
        self.rows.append({"name": item, "item": item, "warehouse": store, "warehouse_reorder_level": level,
                          "warehouse_reorder_qty": qty, "material_request_type": kind})

    def have(self, item, store, projected):
        self.bin[(item, store)] = {"item_code": item, "warehouse": store, "projected_qty": projected, "stock_uom": "Nos"}

    def lot(self, name, item, expires, **per_store):
        self.batch.append({"name": name, "item": item, "expiry_date": expires.isoformat(), "batch_qty": sum(per_store.values()) or 7,
                           "stock_uom": "Nos", "disabled": 0})
        for store, q in per_store.items():
            self.stock[(name, store.replace("_", " "))] = q

    def persons_draft(self, title, items):
        self.n += 1
        name = f"MR-{self.n:03d}"
        self.mr[name] = {"name": name, "title": title, "docstatus": 0, "items": [dict(i) for i in items]}
        return name

    # what the service reads and writes
    def settings(self):
        return dict(self.st)

    def warehouses(self):
        return [dict(w) for w in self.whs]

    def reorder_rows(self):
        return [dict(r) for r in self.rows]

    def bins(self, stores):
        return {k: dict(v) for k, v in self.bin.items() if k[1] in stores}

    def batches(self, last):
        return [dict(b) for b in self.batch if b["expiry_date"] <= last.isoformat()]

    def batch_stock(self, names):
        return None if self.stock is None else {k: v for k, v in self.stock.items() if k[0] in names}

    def open_requests(self):
        return [{"name": d["name"], "title": d["title"], "docstatus": d["docstatus"]} for d in self.mr.values()
                if d["docstatus"] < 2 and not d.get("done")]

    def request(self, name):
        return {**self.mr[name], "items": [dict(i) for i in self.mr[name]["items"]]}

    def insert_request(self, doc):
        self.n += 1
        name = f"MR-{self.n:03d}"
        self.mr[name] = {"name": name, **doc, "items": [dict(i) for i in doc["items"]]}
        self.writes.append(("insert", name, doc.get("docstatus")))
        return self.request(name)

    def update_request(self, name, items):
        self.writes.append(("update", name, None))
        self.mr[name]["items"] = [dict(i) for i in items]
        return self.request(name)

    def alert(self, key):
        return next((a for a in self.alerts if a["alert_key"] == key), None)

    def insert_alert(self, doc):
        if self.fail_alerts:
            self.fail_alerts -= 1
            raise RuntimeError("the shop went away")
        self.alerts.append(dict(doc))
        return True


def run(shop, day=TODAY):
    return R.Service(shop).run(day)


def keys(shop):
    return [a["alert_key"] for a in shop.alerts]


class LowStock(unittest.TestCase):
    def test_a_row_below_its_level_makes_an_alert_and_a_line_from_the_source(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        rep = run(s)
        [mr] = s.mr.values()
        self.assertEqual(mr["title"], f"PP-STK {S1} 2026-10-16")
        self.assertEqual([(i["item_code"], i["qty"], i["from_warehouse"], i["warehouse"]) for i in mr["items"]],
                         [("A", 7.0, HQ, S1)])                   # the shortfall 7 is more than the reorder quantity 4
        [a] = s.alerts
        self.assertEqual((a["kind"], a["store"], a["qty"], a["level"], a["request"]), (A.LOW, S1, 3, 10, mr["name"]))
        self.assertEqual((rep["alerts"], rep["lines_added"]), (1, 1))

    def test_the_reorder_quantity_when_it_is_larger(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=25)
        s.have("A", S1, 9)
        run(s)
        self.assertEqual([i["qty"] for m in s.mr.values() for i in m["items"]], [25.0])

    def test_at_the_level_is_not_low(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 10)
        run(s)
        self.assertEqual((s.alerts, s.mr), ([], {}))

    def test_an_item_with_no_reorder_row_raises_nothing(self):
        s = FakeShop()
        s.have("NOROW", S1, -5)                                 # no row at all: nothing to compare with
        s.reorder("ZERO", S1, level=0, qty=4)                   # a row with no level is no reorder row
        s.have("ZERO", S1, -2)
        run(s)
        self.assertEqual((s.alerts, s.mr), ([], {}))

    def test_a_row_for_a_warehouse_not_watched_raises_nothing(self):
        s = FakeShop(stores=[{"warehouse": S2}])
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 0)
        s.reorder("A", HQ, level=10, qty=4)
        s.have("A", HQ, 0)
        run(s)
        self.assertEqual(s.alerts, [])

    def test_a_purchase_row_alerts_without_a_line(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4, kind="Purchase")
        s.have("A", S1, 1)
        rep = run(s)
        self.assertEqual((len(s.alerts), s.mr, rep["alert_only"]), (1, {}, 1))
        self.assertNotIn("request", s.alerts[0])


class Idempotent(unittest.TestCase):
    def test_a_run_twice_makes_one_alert_per_key_and_one_request(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        s.lot("B1", "MILK", TODAY + dt.timedelta(days=20), Store_1=6)
        run(s)
        rep = run(s)
        self.assertEqual(len(s.alerts), 2)
        self.assertEqual(len(set(keys(s))), 2)
        self.assertEqual(len(s.mr), 1)
        self.assertEqual((rep["alerts"], rep["lines_added"]), (0, 0))

    def test_the_next_day_is_a_new_alert_but_no_second_line_while_the_draft_is_open(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        run(s)
        rep = run(s, TODAY + dt.timedelta(days=1))
        self.assertEqual(len(s.alerts), 2)
        self.assertEqual((len(s.mr), rep["already_on_a_draft"]), (1, 1))
        [mr] = s.mr.values()
        self.assertEqual(s.alerts[1]["request"], mr["name"])

    def test_a_run_that_stopped_before_its_alerts_adds_no_line_twice(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        s.fail_alerts = 1
        with self.assertRaises(RuntimeError):
            run(s)
        run(s)
        [mr] = s.mr.values()
        self.assertEqual((len(mr["items"]), len(s.alerts)), (1, 1))
        self.assertEqual(s.alerts[0]["request"], mr["name"])


class Stamp(unittest.TestCase):
    def test_an_existing_stamped_request_gains_lines(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        run(s)
        s.reorder("B", S1, level=5, qty=5)
        s.have("B", S1, 1)
        run(s)
        [mr] = s.mr.values()
        self.assertEqual([i["item_code"] for i in mr["items"]], ["A", "B"])
        self.assertEqual([w[0] for w in s.writes], ["insert", "update"])

    def test_an_unstamped_request_is_never_touched(self):
        s = FakeShop()
        line = {"item_code": "A", "qty": 99, "from_warehouse": HQ, "warehouse": S1}
        theirs = s.persons_draft("Weekly top-up", [line])
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        run(s)
        self.assertEqual(s.mr[theirs]["items"], [line])
        self.assertNotIn(theirs, [w[1] for w in s.writes])
        ours = [m for m in s.mr.values() if m["name"] != theirs]
        self.assertEqual(len(ours), 1)
        self.assertEqual(s.alerts[0]["request"], ours[0]["name"])

    def test_another_stores_draft_is_not_this_stores(self):
        s = FakeShop()
        s.reorder("A", S2, level=10, qty=4)
        s.have("A", S2, 3)
        run(s)
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        run(s)
        self.assertEqual(sorted(m["title"] for m in s.mr.values()), [f"PP-STK {S1} 2026-10-16", f"PP-STK {S2} 2026-10-16"])

    def test_a_submitted_request_is_left_alone(self):
        s = FakeShop()
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        run(s)
        [first] = s.mr
        s.mr[first]["docstatus"] = 1                       # a person edited the quantity and submitted it
        s.mr[first]["items"][0]["qty"] = 5
        s.reorder("B", S1, level=5, qty=5)
        s.have("B", S1, 1)
        run(s)
        self.assertEqual((s.mr[first]["items"][0]["qty"], len(s.mr[first]["items"])), (5, 1))
        self.assertNotIn(("update", first, None), s.writes)
        self.assertEqual(len(s.mr), 2)

    def test_a_line_on_a_submitted_request_not_yet_moved_is_not_asked_again(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        run(s)
        [first] = s.mr
        s.mr[first]["docstatus"] = 1
        rep = run(s, TODAY + dt.timedelta(days=1))           # the batch has not moved yet: a new alert, no new line
        self.assertEqual((len(s.mr), len(s.alerts), rep["already_on_a_draft"]), (1, 2, 1))
        s.mr[first]["done"] = True                            # transferred; if the batch is still there, ask again
        run(s, TODAY + dt.timedelta(days=2))
        self.assertEqual(len(s.mr), 2)


class NeverSubmitted(unittest.TestCase):
    def test_the_draft_is_never_submitted(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        s.lot("B1", "MILK", TODAY, Store_1=2)
        run(s)
        s.reorder("B", S1, level=5, qty=5)
        s.have("B", S1, 1)
        run(s)
        self.assertTrue(s.mr)
        self.assertEqual({m["docstatus"] for m in s.mr.values()}, {0})
        self.assertEqual({w[2] for w in s.writes if w[0] == "insert"}, {0})


class Expiry(unittest.TestCase):
    def window(self, offset):
        s = FakeShop(expiry_days=20)
        s.lot("B1", "MILK", TODAY + dt.timedelta(days=offset), Store_1=6)
        run(s)
        return s.alerts

    def test_the_window_edges(self):
        self.assertEqual(len(self.window(19)), 1, "the day before the last day")
        self.assertEqual(len(self.window(20)), 1, "the last day")
        self.assertEqual(self.window(21), [], "the day after")

    def test_an_expired_batch_still_in_stock_is_alerted(self):
        self.assertEqual(len(self.window(-3)), 1)

    def test_one_alert_per_store_that_holds_the_batch(self):
        s = FakeShop()
        s.lot("B1", "MILK", TODAY, Store_1=6, Store_2=0, Head_Office=40)
        run(s)
        self.assertEqual([(a["store"], a["qty"], a["store_qty_known"]) for a in s.alerts], [(S1, 6, 1)])

    def test_one_alert_per_store_that_holds_the_batch_and_each_has_its_key(self):
        s = FakeShop()
        s.lot("B1", "MILK", TODAY, Store_1=6, Store_2=2)
        run(s)
        self.assertEqual(sorted((a["store"], a["qty"]) for a in s.alerts), [(S1, 6), (S2, 2)])
        self.assertEqual(len(set(keys(s))), 2)

    def test_alert_only_without_a_clearance_warehouse(self):
        s = FakeShop()
        s.lot("B1", "MILK", TODAY, Store_1=6)
        rep = run(s)
        self.assertEqual((s.mr, rep["alert_only"]), ({}, 1))

    def test_a_clearance_line_from_the_store_when_its_quantity_is_known(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        run(s)
        [mr] = s.mr.values()
        self.assertEqual([(i["item_code"], i["qty"], i["from_warehouse"], i["warehouse"]) for i in mr["items"]],
                         [("MILK", 6, S1, CLR)])
        self.assertEqual(s.alerts[0]["batch"], "B1")

    def test_unknown_per_store_quantity_says_the_total_and_makes_no_line(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        s.stock = None                                   # the key may not read the batch records
        rep = run(s)
        [a] = s.alerts
        self.assertEqual((a.get("store"), a["qty"], a["store_qty_known"], s.mr, rep["known"]), (None, 6, 0, {}, False))


    def test_a_second_batch_of_the_same_item_gets_its_own_line(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        run(s)
        s.lot("B2", "MILK", TODAY + dt.timedelta(days=1), Store_1=9)
        rep = run(s, TODAY + dt.timedelta(days=1))
        lines = sorted((i["qty"], sorted(A.batches_of(i))) for m in s.mr.values() for i in m["items"])
        self.assertEqual(lines, [(6, ["B1"]), (9, ["B2"])])
        self.assertEqual(rep["already_on_a_draft"], 1)


    def test_two_batches_of_one_item_share_one_row_naming_both(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        s.lot("B2", "MILK", TODAY + dt.timedelta(days=2), Store_1=9)
        run(s)
        [mr] = s.mr.values()
        [row] = mr["items"]
        self.assertEqual((row["qty"], A.batches_of(row)), (15, {"B1", "B2"}))
        self.assertEqual({a["request"] for a in s.alerts}, {mr["name"]})
        rep = run(s, TODAY + dt.timedelta(days=1))           # the next day: both batches already named on the open draft
        self.assertEqual((rep["alerts"], rep["lines_added"], rep["already_on_a_draft"], len(s.mr)), (2, 0, 2, 1))

    def test_a_batch_joins_todays_row_for_its_item(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        run(s)
        s.lot("B2", "MILK", TODAY + dt.timedelta(days=2), Store_1=9)
        run(s)
        [mr] = s.mr.values()
        self.assertEqual([(i["qty"], A.batches_of(i)) for i in mr["items"]], [(15.0, {"B1", "B2"})])

    def test_one_item_for_two_moves_keeps_the_first_and_alerts_the_other(self):
        s = FakeShop(clearance_warehouse=CLR)
        s.reorder("MILK", S1, level=10, qty=10)
        s.have("MILK", S1, 6)
        s.lot("B1", "MILK", TODAY, Store_1=6)
        rep = run(s)
        [mr] = s.mr.values()
        self.assertEqual([(i["from_warehouse"], i["warehouse"]) for i in mr["items"]], [(HQ, S1)])
        self.assertEqual(sorted((a["kind"], a.get("request")) for a in s.alerts), [(A.LOW, mr["name"]), (A.EXPIRY, None)])
        self.assertEqual(rep["alert_only"], 1)


class ShopReads(unittest.TestCase):
    """The real Shop's per-store sum, over a stand-in for the record API."""

    class Api:
        def __init__(self, rows):
            self.rows, self.calls, self.bodies = rows, [], []

        def call(self, method, path, params=None, body=None):
            self.calls.append(params)
            if body is not None:
                self.bodies.append(body)
            return {"data": self.rows}

    def test_outward_rows_are_taken_off_and_each_store_is_apart(self):
        api = self.Api([{"warehouse": S1, "batch_no": "B1", "qty": 12}, {"warehouse": S1, "batch_no": "B1", "qty": -5},
                        {"warehouse": S2, "batch_no": "B1", "qty": 3}, {"warehouse": S1, "batch_no": "OTHER", "qty": 50}])
        got = R.Shop(api).batch_stock(["B1"])
        self.assertEqual(got, {("B1", S1): 7.0, ("B1", S2): 3.0})
        self.assertIn('["voucher_type", "!=", "POS Invoice"]', api.calls[0]["filters"])

    def test_an_update_sends_the_rows_and_nothing_else(self):
        api = self.Api({"name": "MR-1"})
        R.Shop(api).update_request("MR-1", [{"item_code": "A"}])
        self.assertEqual(api.bodies, [{"items": [{"item_code": "A"}]}])

    def test_many_batches_are_read_in_parts(self):
        api = self.Api([])
        R.Shop(api).batch_stock([f"B{i}" for i in range(250)])
        self.assertEqual(len(api.calls), 3)


class Settings(unittest.TestCase):
    def test_switched_off_does_nothing(self):
        s = FakeShop(enabled=0)
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        self.assertIn("skipped", run(s))
        self.assertEqual((s.alerts, s.mr), ([], {}))

    def test_the_watched_stores_default_to_every_store_but_source_and_clearance(self):
        st = {"source_warehouse": HQ, "clearance_warehouse": CLR, "stores": []}
        self.assertEqual(A.stores(st, FakeShop().warehouses()), [S1, S2])
        self.assertEqual(A.stores({**st, "stores": [{"warehouse": S2}]}, []), [S2])

    def test_the_user_named_is_on_each_alert(self):
        s = FakeShop(notify_user="buyer@shop.example")
        s.reorder("A", S1, level=10, qty=4)
        s.have("A", S1, 3)
        run(s)
        self.assertEqual(s.alerts[0]["notify_user"], "buyer@shop.example")


if __name__ == "__main__":
    unittest.main()
