"""S30's laptop tests: the migration plan, the migration run against an in-memory shop, and what became of each unit.
No shop, no network.

    python3 -m unittest discover -s samples/s30_units_as_serials/tests -p 'test_*.py'
"""

import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
import migrate as M  # noqa: E402
import units as U  # noqa: E402
from fake_shop import FakeShop  # noqa: E402

CONF = json.load(open(HERE.parent / "config.json"))
MIG = CONF["migration"]
OLD, NEW, STORE = "PP-UNC-OLD-PACK", "PP-USN-PACK", MIG["default_warehouse"]


def unit(code, batch="L1", status="Available", item=OLD):
    return {"unit_code": code, "item": item, "batch": batch, "status": status}


def quiet(*_):
    pass


class Plan(unittest.TestCase):
    def test_codes_go_to_the_new_item_by_batch(self):
        p = U.plan_migration([unit("A1"), unit("A2"), unit("B1", "L2")], {}, MIG)
        self.assertEqual(p["receive"], {(NEW, STORE, "L1-U"): ["A1", "A2"], (NEW, STORE, "L2-U"): ["B1"]})
        self.assertEqual(p["expected"], {(OLD, STORE, "L1"): 2, (OLD, STORE, "L2"): 1})
        self.assertEqual(p["batches"]["L1-U"], {"item": NEW, "from": "L1"})

    def test_sold_missing_and_unmapped_units_are_named(self):
        p = U.plan_migration([unit("S1", status="Sold"), unit("N1", batch=None), unit("X1", item="OTHER"), {"unit_code": ""}], {}, MIG)
        self.assertEqual([e["code"] for e in p["skipped"]], ["S1"])
        self.assertEqual(sorted(e["code"] for e in p["missing"]), ["", "N1", "X1"])
        self.assertEqual(p["receive"], {})

    def test_a_code_on_another_item_is_a_conflict_and_holds_its_lot(self):
        p = U.plan_migration([unit("A1"), unit("A2")], {"A1": {"item_code": "PHONE-9", "batch_no": None}}, MIG)
        self.assertEqual([e["code"] for e in p["conflicts"]], ["A1"])
        self.assertEqual(p["receive"], {(NEW, STORE, "L1-U"): ["A2"]})
        rows, held = U.zero_rows(p, {(OLD, STORE, "L1"): (2, 4.0)}, MIG)
        self.assertEqual(rows, [])
        self.assertEqual(len(held), 1)
        self.assertIn((NEW, STORE, "L1-U"), U.held_receipts(held, MIG))

    def test_a_code_already_moved_is_not_planned_again(self):
        p = U.plan_migration([unit("A1"), unit("A2")], {"A1": {"item_code": NEW, "batch_no": "L1-U", "warehouse": STORE, "status": "Active"}}, MIG)
        self.assertEqual(p["receive"], {(NEW, STORE, "L1-U"): ["A2"]})
        self.assertEqual([e["code"] for e in p["moved"]], ["A1"])

    def test_a_code_whose_receipt_was_cancelled_is_received_again(self):
        # a cancelled receipt leaves the code Inactive, with no store, and its batch kept
        p = U.plan_migration([unit("A1")], {"A1": {"item_code": NEW, "batch_no": "L1-U", "warehouse": None, "status": "Inactive"}}, MIG)
        self.assertEqual((p["receive"], p["moved"]), ({(NEW, STORE, "L1-U"): ["A1"]}, []))

    def test_a_lot_whose_batch_expired_is_held(self):
        p = U.plan_migration([unit("A1")], {}, MIG)
        rows, held = U.zero_rows(p, {(OLD, STORE, "L1"): (1, 4.0)}, MIG, expired={"L1": "2026-01-31"})
        self.assertEqual((rows, len(held)), ([], 1))
        self.assertIn("expired", held[0]["why"])

    def test_two_codes_that_differ_only_in_case_collide(self):
        p = U.plan_migration([unit("ab1"), unit("AB1")], {}, MIG)
        self.assertEqual([e["code"] for e in p["conflicts"]], ["AB1"])

    def test_a_lot_with_packs_without_a_code_is_held(self):
        p = U.plan_migration([unit("A1"), unit("A2")], {}, MIG)
        rows, held = U.zero_rows(p, {(OLD, STORE, "L1"): (24, 4.0)}, MIG)
        self.assertEqual(rows, [])
        self.assertEqual((held[0]["in_stock"], held[0]["with_codes"]), (24, 2))

    def test_a_lot_at_zero_with_codes_still_to_move_is_held(self):
        p = U.plan_migration([unit("A1")], {}, MIG)
        rows, held = U.zero_rows(p, {}, MIG)
        self.assertEqual((rows, len(held)), ([], 1))

    def test_a_matching_lot_is_counted_to_zero_at_its_rate(self):
        p = U.plan_migration([unit("A1"), unit("A2")], {}, MIG)
        rows, held = U.zero_rows(p, {(OLD, STORE, "L1"): (2, 4.5)}, MIG)
        self.assertEqual(held, [])
        self.assertEqual(rows, [{"item_code": OLD, "warehouse": STORE, "batch_no": "L1", "qty": 0, "rate": 4.5}])


class Migrate(unittest.TestCase):
    def shop(self, **kw):
        units = kw.pop("units", [unit("A1"), unit("A2"), unit("B1", "L2"), unit("S1", status="Sold")])
        stock = kw.pop("stock", {(OLD, STORE, "L1"): 2, (OLD, STORE, "L2"): 1})
        return FakeShop(units=units, stock=stock, rates={k: 4.0 for k in stock},
                        batches={"L1": {"item": OLD, "expiry_date": "2027-06-30"}, "L2": {"item": OLD, "expiry_date": "2027-09-30"}}, **kw)

    def test_a_run_moves_the_units_and_counts_the_old_item_to_zero(self):
        s = self.shop()
        out = M.run(s, CONF, apply=True, out=quiet)
        self.assertEqual(out["to_receive"], 3)
        self.assertEqual(sorted(s.sn), ["A1", "A2", "B1"])
        self.assertEqual(s.sn["A1"]["batch_no"], "L1-U")
        self.assertEqual(s.batch["L1-U"]["expiry_date"], "2027-06-30")
        self.assertEqual(s.stock[(OLD, STORE, "L1")], 0)
        self.assertEqual(s.stock[(NEW, STORE, "L1-U")], 2)
        self.assertEqual({r["basic_rate"] for d in s.inserted("Stock Entry") for r in d["items"]}, {4.0})
        self.assertEqual({r["expense_account"] for d in s.inserted("Stock Entry") for r in d["items"]}, {"Stock Adjustment - DR"},
                         "the receipt must post where the count to 0 posts, not to an item's own expense account")

    def test_run_twice_and_nothing_doubles(self):
        s = self.shop()
        M.run(s, CONF, apply=True, out=quiet)
        docs = len(s.docs)
        again = M.run(s, CONF, apply=True, out=quiet)
        self.assertEqual((again["to_receive"], again["moved_before"], again["lots_to_zero"]), (0, 3, 0))
        self.assertEqual(len(s.docs), docs, "a second run wrote something")
        self.assertEqual(s.stock[(NEW, STORE, "L1-U")], 2)

    def test_a_crash_after_the_receipt_finishes_on_the_next_run(self):
        s = self.shop()
        real = s.insert

        def no_count(dt, doc):
            if dt == "Stock Reconciliation":
                raise RuntimeError("down")
            return real(dt, doc)
        s.insert = no_count
        with self.assertRaises(RuntimeError):
            M.run(s, CONF, apply=True, out=quiet)
        s.insert = real
        again = M.run(s, CONF, apply=True, out=quiet)
        self.assertEqual((again["to_receive"], again["lots_to_zero"]), (0, 2))
        self.assertEqual(s.stock[(OLD, STORE, "L1")], 0)
        self.assertEqual(s.stock[(NEW, STORE, "L1-U")], 2)

    def test_a_code_already_on_another_item_is_never_made_twice(self):
        s = self.shop(serials={"A1": {"name": "A1", "item_code": "PHONE-9", "batch_no": None, "warehouse": STORE, "status": "Active"}})
        out = M.run(s, CONF, apply=True, out=quiet)
        self.assertEqual(out["conflicts"], 1)
        self.assertEqual(s.sn["A1"]["item_code"], "PHONE-9")
        self.assertNotIn((NEW, STORE, "L1-U"), s.stock, "the held lot's other units were received")
        self.assertEqual(s.stock[(OLD, STORE, "L1")], 2, "the held lot was counted to 0")
        self.assertEqual(s.stock[(OLD, STORE, "L2")], 0)

    def test_an_expired_old_batch_is_held_and_nothing_of_it_moves(self):
        s = self.shop()
        s.batch["L1"]["expiry_date"] = "2020-01-31"
        out = M.run(s, CONF, apply=True, out=quiet)
        self.assertEqual(out["lots_held"], 1)
        self.assertNotIn((NEW, STORE, "L1-U"), s.stock)
        self.assertEqual(s.stock[(OLD, STORE, "L1")], 2)

    def test_a_dry_run_writes_nothing(self):
        s = self.shop()
        M.run(s, CONF, apply=False, out=quiet)
        self.assertEqual(s.docs, [])


def sn(name, status="Active", wh="Store 1", item=NEW, batch="L1-U"):
    return {"name": name, "item_code": item, "batch_no": batch, "warehouse": wh, "status": status}


def mv(vt, kind, day, t="10:00:00", c=None, no="DOC"):
    return {"voucher_type": vt, "voucher_no": no, "type_of_transaction": kind, "posting_date": day, "posting_time": t,
            "creation": c or f"{day} {t}"}


RECEIPT = mv("Stock Entry", "Inward", "2026-10-01")


class Classify(unittest.TestCase):
    def test_a_unit_the_count_did_not_find_is_counted_out(self):
        r = U.classify(sn("A1", "Delivered", None), [RECEIPT, mv(U.COUNT, "Outward", "2026-10-05", no="REC-1")], set())
        self.assertEqual((r["result"], r["voucher_no"]), (U.COUNTED_OUT, "REC-1"))

    def test_a_unit_present_at_the_count_is_in_stock(self):
        # the count takes every unit out, then puts the counted ones back in, at the same time
        moves = [RECEIPT, mv(U.COUNT, "Outward", "2026-10-05", c="2026-10-05 10:00:00.1"),
                 mv(U.COUNT, "Inward", "2026-10-05", c="2026-10-05 10:00:00.2")]
        self.assertEqual(U.classify(sn("A1"), moves, set())["result"], U.IN_STOCK)

    def test_a_sale_after_a_count_is_sold_not_counted_out(self):
        moves = [RECEIPT, mv(U.COUNT, "Outward", "2026-10-05"), mv(U.COUNT, "Inward", "2026-10-05", c="2026-10-05 10:00:01"),
                 mv("Sales Invoice", "Outward", "2026-10-06", no="SINV-1")]
        r = U.classify(sn("A1", "Delivered", None), moves, set())
        self.assertEqual((r["result"], r["voucher_no"]), (U.SOLD, "SINV-1"))

    def test_a_morning_sale_and_return_then_an_afternoon_count_is_counted_out(self):
        # the shop writes 9:30 as "9:30:00": as text it would sort after "14:00:00"
        moves = [RECEIPT, mv("Sales Invoice", "Outward", "2026-10-05", "9:30:00", c="x"), mv("Sales Invoice", "Inward", "2026-10-05", "9:45:00", c="x"),
                 mv(U.COUNT, "Outward", "2026-10-05", "14:00:00", c="x", no="REC-9")]
        r = U.classify(sn("A1", "Delivered", None), moves, set())
        self.assertEqual((r["result"], r["voucher_no"]), (U.COUNTED_OUT, "REC-9"))

    def test_a_till_sale_with_the_day_open_reads_so(self):
        r = U.classify(sn("A1"), [RECEIPT, mv("POS Invoice", "Outward", "2026-10-06")], set())
        self.assertEqual(r["result"], U.SOLD_DAY_OPEN)

    def test_a_till_return_puts_it_back_in_stock(self):
        moves = [RECEIPT, mv("POS Invoice", "Outward", "2026-10-06"), mv("POS Invoice", "Inward", "2026-10-06", "11:00:00")]
        self.assertEqual(U.classify(sn("A1"), moves, set())["result"], U.IN_STOCK)

    def test_defective_issued_and_not_received(self):
        self.assertEqual(U.classify(sn("A1", wh="Defective"), [RECEIPT], {"Defective"})["result"], U.DEFECTIVE)
        self.assertEqual(U.classify(sn("A1", "Consumed", None), [RECEIPT, mv("Stock Entry", "Outward", "2026-10-07")], set())["result"], U.ISSUED)
        self.assertEqual(U.classify(sn("A1", "Inactive", None), [], set())["result"], U.NOT_RECEIVED)

    def test_the_report_counts_every_result(self):
        rep = U.report([sn("A1"), sn("A2", "Delivered", None)], {"A2": [RECEIPT, mv(U.COUNT, "Outward", "2026-10-05")]}, set())
        self.assertEqual((rep["counts"][U.IN_STOCK], rep["counts"][U.COUNTED_OUT]), (1, 1))
        self.assertEqual(sum(rep["counts"].values()), 2)


if __name__ == "__main__":
    unittest.main()
