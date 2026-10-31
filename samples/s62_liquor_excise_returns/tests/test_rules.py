"""S62's pure core: where each movement goes, each item's balance from its last ledger row, the count difference, the
volume and pure alcohol, the unit, the period, the press's body and signature, and the words.

    python3 -m unittest discover -s samples/s62_liquor_excise_returns/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import os
import sys
import unittest
from decimal import Decimal as D

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import exr  # noqa: E402

GIN = {"item_name": "Gin", "class": "Spirits", "litres": D("0.7"), "abv": D(40)}


class Kinds(unittest.TestCase):
    def test_each_voucher_type_and_purpose_has_its_line(self):
        cases = [("Sales Invoice", -1, None, exr.SOLD), ("POS Invoice", -1, None, exr.SOLD),
                 ("Delivery Note", -1, None, exr.SOLD), ("Sales Invoice", 1, None, exr.RETURNED_IN),
                 ("POS Invoice", 1, None, exr.RETURNED_IN), ("Purchase Receipt", 1, None, exr.RECEIVED),
                 ("Purchase Invoice", 1, None, exr.RECEIVED), ("Purchase Receipt", -1, None, exr.RETURNED_OUT),
                 ("Stock Entry", 1, "Material Transfer", exr.TRANSFERRED_IN),
                 ("Stock Entry", -1, "Material Transfer", exr.TRANSFERRED_OUT),
                 ("Stock Entry", 1, "Material Receipt", exr.RECEIVED), ("Stock Entry", -1, "Material Issue", exr.WRITTEN_OFF),
                 ("Stock Entry", -1, "Material Receipt", exr.OTHER_OUT), ("Stock Entry", 1, "Material Issue", exr.OTHER_IN),
                 ("Stock Entry", 1, "Repack", exr.OTHER_IN), ("Stock Entry", -1, None, exr.OTHER_OUT),
                 ("Subcontracting Receipt", 1, None, exr.OTHER_IN), ("Asset Capitalization", -1, None, exr.OTHER_OUT)]
        for vtype, qty, purpose, want in cases:
            self.assertEqual(exr.kind_of(vtype, D(qty), purpose), want, (vtype, qty, purpose))

    def test_twelve_movements_in_their_order(self):
        self.assertEqual(exr.MOVEMENTS, ("Opening stock", "Received from suppliers", "Transferred in", "Returned by customers",
                                         "Other in", "Sold", "Transferred out", "Returned to suppliers", "Written off",
                                         "Other out", "Count difference", "Closing stock"))


class Balances(unittest.TestCase):
    def test_the_last_row_at_the_items_last_time_by_creation(self):
        ats = [{"item_code": "A", "at": "2026-10-14 10:28:24"}, {"item_code": "B", "at": "2026-10-14 18:59:35"}]
        rows = [{"name": "1", "item_code": "A", "posting_datetime": "2026-10-14 10:28:24", "creation": "2026-10-14 10:28:24.1",
                 "qty_after_transaction": 5},
                {"name": "2", "item_code": "A", "posting_datetime": "2026-10-14 10:28:24", "creation": "2026-10-14 10:28:24.3",
                 "qty_after_transaction": 7},
                {"name": "3", "item_code": "A", "posting_datetime": "2026-10-14 18:59:35", "creation": "2026-10-14 18:59:36.0",
                 "qty_after_transaction": 99},        # B's time, A's row: not A's last
                {"name": "4", "item_code": "B", "posting_datetime": "2026-10-14 18:59:35", "creation": "2026-10-14 18:59:36.0",
                 "qty_after_transaction": 0}]
        self.assertEqual(exr.last_balances(ats, rows), {"A": D(7), "B": D(0)})

    def test_microseconds_and_no_row_and_a_bad_time(self):
        ats = [{"item_code": "A", "at": "2026-10-14 10:28:24.500000"}, {"item_code": "B", "at": "2026-10-14 10:00:00"},
               {"item_code": "C", "at": "not a time"}]
        rows = [{"item_code": "A", "posting_datetime": "2026-10-14 10:28:24.5", "creation": "x", "qty_after_transaction": "3.5"}]
        self.assertEqual(exr.last_balances(ats, rows), {"A": D("3.5")})


class WorkOut(unittest.TestCase):
    def test_a_count_is_what_is_left_and_the_figures_close(self):
        lines, missing, n, _ = exr.work_out({"G": GIN}, {"G": D(10)}, {"G": D(6)},
                                         [{"item_code": "G", "voucher_type": "Sales Invoice", "qty": -3}], [], {}, "Litres")
        f = {ln["movement"]: (ln["units"], ln["volume"], ln["pure_alcohol"]) for ln in lines}
        self.assertEqual(f[exr.COUNT], (D("-1.000"), D("-0.700"), D("-0.280")))
        self.assertEqual(f[exr.SOLD], (D("3.000"), D("2.100"), D("0.840")))
        self.assertEqual((missing, n, len(lines)), ([], 1, 12))
        self.assertTrue(exr.work_out({"G": GIN}, {"G": D(10)}, {"G": D(6)},
                                     [{"item_code": "G", "voucher_type": "Sales Invoice", "qty": -3}], [], {}, "Litres")[3])

    def test_stock_entries_net_per_entry_and_by_purpose(self):
        entries = [{"item_code": "G", "voucher_no": "E1", "qty": -2}, {"item_code": "G", "voucher_no": "E1", "qty": 2},
                   {"item_code": "G", "voucher_no": "E2", "qty": -1}, {"item_code": "G", "voucher_no": "E3", "qty": 4}]
        lines, _, _, _ = exr.work_out({"G": GIN}, {}, {"G": D(3)}, [], entries, {"E1": "Material Transfer",
                                                                              "E2": "Material Issue"}, "Litres")
        f = {ln["movement"]: ln["units"] for ln in lines}
        self.assertEqual((f[exr.TRANSFERRED_OUT], f[exr.WRITTEN_OFF], f[exr.OTHER_IN], f[exr.COUNT]),
                         (D(0), D(1), D(4), D(0)))

    def test_counts_and_entries_are_never_read_from_the_voucher_type_totals(self):
        moves = [{"item_code": "G", "voucher_type": "Stock Reconciliation", "qty": 5},
                 {"item_code": "G", "voucher_type": "Stock Entry", "qty": 5}]
        lines, _, _, _ = exr.work_out({"G": GIN}, {}, {"G": D(5)}, moves, [], {}, "Litres")
        f = {ln["movement"]: ln["units"] for ln in lines}
        self.assertEqual((f[exr.OTHER_IN], f[exr.RECEIVED], f[exr.COUNT]), (D(0), D(0), D(5)))

    def test_items_without_a_class_or_any_figure_are_left_out(self):
        lines, _, n, _ = exr.work_out({"G": GIN}, {"X": D(9)}, {}, [{"item_code": "X", "voucher_type": "Sales Invoice",
                                                                 "qty": -1}], [], {}, "Litres")
        self.assertEqual((lines, n), ([], 0))

    def test_missing_litres_or_strength_counts_units_and_names_the_item(self):
        items = {"R": {"item_name": "Rum", "class": "Spirits", "litres": None, "abv": D(40)},
                 "W": {"item_name": "Wine", "class": "Wine", "litres": D("0.75"), "abv": None}}
        lines, missing, _, _ = exr.work_out(items, {"R": D(2), "W": D(4)}, {"R": D(2), "W": D(4)}, [], [], {}, "Litres")
        f = {(ln["duty_class"], ln["movement"]): (ln["units"], ln["volume"], ln["pure_alcohol"]) for ln in lines}
        self.assertEqual(f[("Spirits", exr.OPENING)], (D(2), D(0), D(0)))
        self.assertEqual(f[("Wine", exr.OPENING)], (D(4), D("3.000"), D(0)))
        self.assertEqual(missing, ["Rum", "Wine"])

    def test_us_gallons_and_rounding_once_per_line_half_up(self):
        items = {k: dict(GIN, litres=D("0.0375"), abv=D(40)) for k in ("A", "B")}
        lines, _, _, _ = exr.work_out(items, {"A": D(1), "B": D(1)}, {"A": D(1), "B": D(1)}, [], [], {}, "Litres")
        self.assertEqual(lines[0]["volume"], D("0.075"))          # 2 x 0.0375 summed first, never 0.038 + 0.038
        self.assertEqual(lines[0]["pure_alcohol"], D("0.030"))
        lines, _, _, _ = exr.work_out({"A": dict(GIN, litres=D("0.25"), abv=D(25))}, {"A": D(1)}, {"A": D(1)}, [], [], {}, "Litres")
        self.assertEqual(lines[0]["pure_alcohol"], D("0.063"))    # 0.0625: half up, never the even 0.062
        lines, _, _, _ = exr.work_out({"A": dict(GIN, litres=D(1))}, {"A": D(1)}, {"A": D(1)}, [], [], {}, "US gallons")
        self.assertEqual(lines[0]["volume"], D("0.264"))          # 1 / 3.785411784 = 0.26417…
        with self.assertRaises(ValueError):
            exr.work_out({}, {}, {}, [], [], {}, "Gallons")

    def test_each_printed_column_adds_up_after_rounding(self):
        wine = {"item_name": "Wine", "class": "Wine", "litres": D("0.75"), "abv": D("12.5")}
        lines, _, _, _ = exr.work_out({"W": wine, "V": dict(wine)}, {"W": D(2)}, {"W": D(3), "V": D(1)},
                                   [{"item_code": "W", "voucher_type": "Purchase Receipt", "qty": 1},
                                    {"item_code": "V", "voucher_type": "Purchase Receipt", "qty": 1}], [], {}, "Litres")
        f = {ln["movement"]: ln for ln in lines}
        for col in ("units", "volume", "pure_alcohol"):
            self.assertEqual(f[exr.OPENING][col] + sum(f[m][col] for m in exr.INS) - sum(f[m][col] for m in exr.OUTS)
                             + f[exr.COUNT][col], f[exr.CLOSING][col], col)
        self.assertEqual(f[exr.CLOSING]["pure_alcohol"], D("0.375"))   # 0.28125 + 0.09375, rounded once
        self.assertEqual((f[exr.COUNT]["units"], f[exr.COUNT]["pure_alcohol"]), (D(0), D("-0.001")))
        self.assertNotIn("Stock counts", exr.summary_of(lines, [], 2, "Litres", False))   # rounding alone is no count

    def test_a_count_whose_units_net_to_nothing_is_still_said(self):
        bottle = {"item_name": "Wine 75cl", "class": "Wine", "litres": D("0.75"), "abv": D(12)}
        litre = {"item_name": "Wine 1L", "class": "Wine", "litres": D(1), "abv": D(12)}
        lines, missing, n, counts = exr.work_out({"B": bottle, "L": litre}, {"B": D(5), "L": D(5)},
                                                 {"B": D(6), "L": D(4)}, [], [], {}, "Litres")
        f = {ln["movement"]: ln for ln in lines}
        self.assertEqual((f[exr.COUNT]["units"], f[exr.COUNT]["volume"], counts), (D(0), D("-0.250"), True))
        self.assertIn("Stock counts changed -0.250 litres in all.", exr.summary_of(lines, missing, n, "Litres", counts))

    def test_the_class_code_rides_each_line(self):
        lines, _, _, _ = exr.work_out({"G": GIN}, {"G": D(1)}, {"G": D(1)}, [], [], {}, "Litres", {"Spirits": "S1"})
        self.assertEqual({ln["return_code"] for ln in lines}, {"S1"})


class Items(unittest.TestCase):
    def test_millilitres_to_litres_and_the_bounds(self):
        f = exr.FIELD
        self.assertEqual(exr.item_of({"name": "X", f + "class": "Spirits", f + "ml": 37.5, f + "abv": 40})["litres"],
                         D("0.0375"))
        for ml, abv, want in ((0, 40, (None, D(40))), (-5, 40, (None, D(40))), ("", 40, (None, D(40))),
                              (750, 0, (D("0.75"), None)), (750, 101, (D("0.75"), None)), (750, True, (D("0.75"), None))):
            it = exr.item_of({"name": "X", f + "class": "C", f + "ml": ml, f + "abv": abv})
            self.assertEqual((it["litres"], it["abv"]), want, (ml, abv))
        self.assertEqual(exr.item_of({"name": "X"})["item_name"], "X")


class Period(unittest.TestCase):
    def test_bounds_and_refusals(self):
        self.assertEqual(exr.period("2026-10-01", "2026-10-31"), ("2026-10-01 00:00:00", "2026-11-01 00:00:00"))
        self.assertEqual(exr.period("2024-01-01", "2024-12-31"), ("2024-01-01 00:00:00", "2025-01-01 00:00:00"))
        self.assertIsInstance(exr.period("2024-01-01", "2025-01-01"), str)
        self.assertIsInstance(exr.period("2026-10-02", "2026-10-01"), str)
        self.assertIsInstance(exr.period(None, "2026-10-01"), str)
        self.assertIsInstance(exr.period("2026-13-01", "2026-10-01"), str)


class Press(unittest.TestCase):
    def test_return_of_takes_one_return(self):
        ctx = {"v": 1, "user": "u", "records": [{"doctype": exr.RETURN, "name": "EXR-R-00001"}]}
        self.assertEqual(exr.return_of({"point": "desk_action/1", "context": ctx}), ("EXR-R-00001", "u"))
        two = [{"doctype": exr.RETURN, "name": "EXR-R-00001"}, {"doctype": exr.RETURN, "name": "EXR-R-00002"}]
        for bad in ({"point": "x", "context": ctx}, {"point": "desk_action/1", "context": dict(ctx, records=[])},
                    {"point": "desk_action/1", "context": dict(ctx, records=two)},
                    {"point": "desk_action/1", "context": dict(ctx, records=[{"doctype": exr.CLASS, "name": "x"}])},
                    {"point": "desk_action/1", "context": dict(ctx, records=[{"doctype": exr.RETURN, "name": ""}])}):
            with self.assertRaises(ValueError):
                exr.return_of(bad)

    def test_verify(self):
        raw, ts = b'{"a":1}', "1700000000"
        sig = base64.b64encode(hmac.new(b"s", ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(exr.verify(ts, sig, raw, "s", now=1700000000), "")
        self.assertNotEqual(exr.verify(ts, sig, raw, "other", now=1700000000), "")
        self.assertNotEqual(exr.verify(ts, sig, raw, "s", now=1700000000 + 301), "")
        self.assertNotEqual(exr.verify("", sig, raw, "s", now=1700000000), "")


class Words(unittest.TestCase):
    def test_the_summary_in_full(self):
        lines, missing, n, counts = exr.work_out({"G": GIN}, {"G": D(10)}, {"G": D(7)},
                                         [{"item_code": "G", "voucher_type": "POS Invoice", "qty": -3}], [], {}, "Litres")
        self.assertEqual(exr.summary_of(lines, missing, n, "Litres", counts),
                         "1 duty class, 1 item. Sold 2.100 litres (0.840 litres of pure alcohol); closing stock 4.900 litres.")
        many = [f"Item {i}" for i in range(5)]
        self.assertEqual(exr.summary_of(lines, many, n, "US gallons", counts),
                         "1 duty class, 1 item. Sold 2.100 US gallons (0.840 US gallons of pure alcohol); closing stock "
                         "4.900 US gallons. 5 items have no millilitres or no strength, so their volume or pure alcohol is left "
                         "out (units counted): Item 0, Item 1, Item 2 and 2 more.")
        self.assertTrue(exr.summary_of([], [], 0, "Litres").startswith("Nothing to return:"))

    def test_a_message_is_cut_to_its_length(self):
        m = exr.message("x" * 400)["message"]
        self.assertEqual((len(m["body"]), m["title"], m["level"]), (280, "Liquor excise returns", "success"))


class Prefix(unittest.TestCase):
    def tearDown(self):
        exr.use_prefix("PP EXR")

    def test_every_name_follows(self):
        exr.use_prefix("IVENDNEXT EXR")
        self.assertEqual((exr.CLASS, exr.RETURN, exr.LINE, exr.FIELD, exr.DRAFT, exr.FILED, exr.DROPPED, exr.LOCK_RULE),
                         ("IVENDNEXT EXR Duty Class", "IVENDNEXT EXR Return", "IVENDNEXT EXR Return Line", "ivendnext_exr_",
                          "IVENDNEXT EXR Draft", "IVENDNEXT EXR Filed", "IVENDNEXT EXR Dropped",
                          "IVENDNEXT EXR return locked once filed"))


if __name__ == "__main__":
    unittest.main()
