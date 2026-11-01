"""S62's service against a stand-in retailer (``fakeshop.py``): a press checked by its signature, *Work out the return*
writing exactly the twelve lines per duty class a store's October gives (openings after a September count, receipts,
till sales, a customer return, transfers both ways, breakage, a supplier return, a repack, a count in the period;
cancelled rows, another store's rows, items with no class and a sale one second after the period left out), the
summary, the unit, and every refusal said in words with nothing written.

    python3 -m unittest discover -s samples/s62_liquor_excise_returns/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import app  # noqa: E402
import exr  # noqa: E402
from fakeshop import FakeShop  # noqa: E402

CONF = {"PP_WORK_SECRET": "w-secret", "PP_ADMIN_TOKEN": "t"}
ITEM = "pp_exr_"
NAME = "EXR-R-00001"


def body(name=NAME, user="stock@shop.example", doctype=None):
    return json.dumps({"point": "desk_action/1", "context": {
        "v": 1, "action": "x", "label": "x", "user": user, "lang": "en", "inputs": {}, "idempotency_key": "k",
        "records": [{"doctype": doctype or exr.RETURN, "name": name, "fields": {"name": name}}]}}).encode()


def signed(raw, secret, ts=None):
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}


def item(name, item_name, cls=None, ml=None, abv=None):
    return {"name": name, "item_name": item_name, ITEM + "class": cls, ITEM + "ml": ml, ITEM + "abv": abv}


def shop():
    """Store A's October. Openings: gin 20, vodka 10, wine 10 (counted down from 12 on 30 September), beer 5, rum 6."""
    s = FakeShop()
    s.classes = [{"name": "Spirits", "return_code": "S1"}, {"name": "Wine", "return_code": "W1"},
                 {"name": "Beer", "return_code": ""}, {"name": "Cider", "return_code": "C1"}]
    s.items = [item("GIN", "Gin 70cl", "Spirits", 700, 40), item("VODKA", "Vodka 1L", "Spirits", 1000, 37.5),
               item("WINE", "Red wine", "Wine", 750, 12.5), item("BEER6", "Lager 6-pack", "Beer", 1980, 5),
               item("RUM", "Rum", "Spirits", None, 40), item("SODA", "Soda")]
    for it, q in (("GIN", 24), ("WINE", 12), ("VODKA", 10), ("BEER6", 5), ("RUM", 6), ("SODA", 50)):
        s.move(it, "2026-09-01 10:00:00", "Purchase Receipt", "PR-1", q)
    s.move("GIN", "2026-09-15 12:00:00", "Sales Invoice", "SINV-0", -4)
    s.move("GIN", "2026-09-20 12:00:00", "Sales Invoice", "SINV-C", -100, cancelled=1)
    s.count("WINE", "2026-09-30 18:00:00", 10, vno="SR-0")
    s.move("BEER6", "2026-09-10 10:00:00", "Purchase Receipt", "PR-B", 100, store="Store B")   # another store's opening
    # October
    s.move("GIN", "2026-10-01 00:00:00", "Purchase Receipt", "PR-2", 12)
    for it, q in (("GIN", -5), ("WINE", -3), ("BEER6", -2), ("RUM", -1), ("SODA", -10)):
        s.move(it, "2026-10-03 21:00:00", "Sales Invoice", "SINV-1", q)          # the till day's combined invoice
    s.move("GIN", "2026-10-04 21:00:00", "Sales Invoice", "SINV-2", 1)              # its credit note: a customer's return
    s.move("VODKA", "2026-10-05 11:00:00", "Delivery Note", "DN-1", -2)
    s.entry("STE-1", "Material Transfer")
    s.move("GIN", "2026-10-06 09:00:00", "Stock Entry", "STE-1", -3)
    s.move("GIN", "2026-10-06 09:00:00", "Stock Entry", "STE-1", 3, store="Store B")
    s.entry("STE-2", "Material Transfer")
    s.move("VODKA", "2026-10-07 09:00:00", "Stock Entry", "STE-2", -4, store="Store B")
    s.move("VODKA", "2026-10-07 09:00:00", "Stock Entry", "STE-2", 4)
    s.entry("STE-3", "Material Issue")
    s.move("WINE", "2026-10-08 09:00:00", "Stock Entry", "STE-3", -1)               # breakage
    s.move("WINE", "2026-10-09 09:00:00", "Purchase Receipt", "PR-3", -2)            # back to the supplier
    s.entry("STE-4", "Material Receipt")
    s.move("BEER6", "2026-10-10 09:00:00", "Stock Entry", "STE-4", 3)
    s.entry("STE-5", "Repack")
    s.move("GIN", "2026-10-11 09:00:00", "Stock Entry", "STE-5", -1)
    s.entry("STE-6", "Material Transfer")                                            # bin to bin in the same store
    s.move("GIN", "2026-10-12 09:00:00", "Stock Entry", "STE-6", -2)
    s.move("GIN", "2026-10-12 09:00:00", "Stock Entry", "STE-6", 2)
    s.move("GIN", "2026-10-15 12:00:00", "Sales Invoice", "SINV-X", -50, cancelled=1)
    s.count("GIN", "2026-10-20 18:00:00", 22, vno="SR-1")                            # 24 on the shelf before: -2
    s.move("WINE", "2026-10-20 10:00:00", "Purchase Receipt", "PR-B2", 6, store="Store B")   # another store's closing
    s.move("GIN", "2026-10-25 21:00:00", "Sales Invoice", "SINV-3", -2)
    s.move("WINE", "2026-10-31 23:59:59", "Sales Invoice", "SINV-4", -1)            # the period's last second
    s.move("GIN", "2026-11-01 00:00:00", "Sales Invoice", "SINV-5", -7)              # the next period's first
    s.ret(NAME)
    return s


D = Decimal
# (class, movement): (units, volume, pure alcohol), in litres, worked out by hand
WANT = {
    ("Beer", "Opening stock"): ("5", "9.900", "0.495"), ("Beer", "Received from suppliers"): ("3", "5.940", "0.297"),
    ("Beer", "Sold"): ("2", "3.960", "0.198"), ("Beer", "Closing stock"): ("6", "11.880", "0.594"),
    ("Spirits", "Opening stock"): ("36", "24.000", "9.350"), ("Spirits", "Received from suppliers"): ("12", "8.400", "3.360"),
    ("Spirits", "Transferred in"): ("4", "4.000", "1.500"), ("Spirits", "Returned by customers"): ("1", "0.700", "0.280"),
    ("Spirits", "Sold"): ("10", "6.900", "2.710"), ("Spirits", "Transferred out"): ("3", "2.100", "0.840"),
    ("Spirits", "Other out"): ("1", "0.700", "0.280"), ("Spirits", "Count difference"): ("-2", "-1.400", "-0.560"),
    ("Spirits", "Closing stock"): ("37", "26.000", "10.100"),
    ("Wine", "Opening stock"): ("10", "7.500", "0.938"), ("Wine", "Sold"): ("4", "3.000", "0.375"),
    ("Wine", "Returned to suppliers"): ("2", "1.500", "0.188"), ("Wine", "Written off"): ("1", "0.750", "0.094"),
    ("Wine", "Closing stock"): ("3", "2.250", "0.281"),
}
SUMMARY = ("3 duty classes, 5 items. Sold 13.860 litres (3.283 litres of pure alcohol); closing stock 40.130 litres. "
           "Stock counts changed -1.400 litres in all. 1 item has no millilitres or no strength, so its volume or pure alcohol is "
           "left out (units counted): Rum.")


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.s = shop()
        self.svc = app.Service(CONF, self.s, now=lambda: __import__("datetime").datetime(2026, 11, 2, 9, 30))

    def tearDown(self):
        exr.use_prefix("PP EXR")

    def press(self, name=NAME, secret=None, user="stock@shop.example"):
        raw = body(name, user)
        return self.svc.handle("POST", "/exr/work", signed(raw, secret or CONF["PP_WORK_SECRET"]), raw)

    def lines(self, name=NAME):
        return {(r["duty_class"], r["movement"]): (r["units"], r["volume"], r["pure_alcohol"])
                for r in self.s.returns[name]["lines"]}

    def test_s1_work_out_writes_twelve_lines_per_class_from_the_stores_ledger(self):
        code, out = self.press()
        self.assertEqual(code, 200, out)
        got = self.lines()
        self.assertEqual(len(self.s.returns[NAME]["lines"]), 36)          # Beer, Spirits, Wine; Cider has no item
        self.assertEqual([r["movement"] for r in self.s.returns[NAME]["lines"][:12]], list(exr.MOVEMENTS))
        self.assertEqual([r["duty_class"] for r in self.s.returns[NAME]["lines"][::12]], ["Beer", "Spirits", "Wine"])
        want = {k: tuple(float(D(x)) for x in v) for k, v in WANT.items()}
        self.assertEqual({k: v for k, v in got.items() if any(v)}, want)
        self.assertEqual({r["return_code"] for r in self.s.returns[NAME]["lines"] if r["duty_class"] == "Spirits"}, {"S1"})
        r = self.s.returns[NAME]
        self.assertEqual((r["summary"], r["worked_out_by"], r["worked_out_at"]),
                         (SUMMARY, "stock@shop.example", "2026-11-02 09:30 UTC"))
        self.assertEqual((out["message"]["body"], out["message"]["level"], out.get("refresh")), (SUMMARY, "success", True))

    def test_s1b_each_class_adds_up_opening_plus_in_less_out_plus_counts_to_closing(self):
        self.press()
        for cls in ("Beer", "Spirits", "Wine"):
            for col in (0, 1, 2):
                f = {m: D(str(self.lines().get((cls, m), (0, 0, 0))[col])) for m in exr.MOVEMENTS}
                total = f[exr.OPENING] + sum(f[m] for m in exr.INS) - sum(f[m] for m in exr.OUTS) + f[exr.COUNT]
                self.assertLessEqual(abs(total - f[exr.CLOSING]), D("0.003"), (cls, col))

    def test_s2_the_reads_are_few_and_never_a_row_a_sale(self):
        self.press()
        self.assertEqual(len(self.s.reads), 11, self.s.reads)       # the return, the lock, classes, items, 5 grouped, the balances, purposes
        ledger = [r for r in self.s.reads if r[1] == "Stock Ledger Entry"]
        grouped = [r for r in ledger if r[3]]
        self.assertEqual(len(grouped), 5, ledger)                   # two last times, in, out, the entries
        self.assertEqual({r[2] for r in ledger if not r[3]},
                         {("name", "item_code", "posting_datetime", "creation", "qty_after_transaction")})
        self.assertNotIn("customer", json.dumps(self.s.reads))
        self.assertEqual(self.s.reads[3][2], ("name", "item_name", ITEM + "class", ITEM + "ml", ITEM + "abv"))

    def test_s3_us_gallons(self):
        self.s.returns[NAME]["unit"] = "US gallons"
        self.press()
        got = self.lines()
        self.assertEqual(got[("Spirits", "Closing stock")],
                         (37.0, float((D(26) / exr.GALLON).quantize(exr.PLACES)), float((D("10.1") / exr.GALLON).quantize(exr.PLACES))))
        self.assertIn("US gallons", self.s.returns[NAME]["summary"])

    def test_s4_a_store_with_no_ledger_is_refused_and_one_with_no_liquor_says_so(self):
        self.s.returns[NAME]["store"] = "Store C"          # a group of warehouses, or a user permission: no rows at all
        code, out = self.press()
        self.assertEqual((code, out["message"]["body"], out["message"]["level"], self.s.writes),
                         (200, app.EMPTY_STORE, "warning", []))
        self.s.move("SODA", "2026-10-02 10:00:00", "Purchase Receipt", "PR-C", 5, store="Store C")
        code, out = self.press()                             # a store whose stock has no duty class
        self.assertEqual((code, self.s.returns[NAME]["lines"], out["message"]["level"]), (200, [], "info"))
        self.assertTrue(out["message"]["body"].startswith("Nothing to return: no item with a duty class"))

    def test_s4b_reads_stay_short_for_a_store_of_many_items(self):
        for i in range(400):                               # 400 liquor items, each moved at its own second
            code = f"WINE-{i:03d}"
            self.s.items.append(item(code, f"Wine {i}", "Wine", 750, 12.5))
            self.s.move(code, f"2026-09-{1 + i % 28:02d} 10:{i // 60:02d}:{i % 60:02d}.{i:06d}", "Purchase Receipt", "PR-W", 6)
            self.s.move(code, f"2026-10-{1 + i % 28:02d} 11:{i // 60:02d}:{i % 60:02d}.{i:06d}", "Sales Invoice", "SINV-W", -1)
        sizes = []
        orig = self.s.rows

        def rows(doctype, fields, filters, group_by=None, timeout=None):
            q = {"fields": fields, "filters": filters, "limit_page_length": 0}
            if group_by:
                q["group_by"] = group_by
            sizes.append(len(app.urllib.parse.urlencode({k: app.json.dumps(v) if not isinstance(v, (str, int)) else v
                                                         for k, v in q.items()})))
            return orig(doctype, fields, filters, group_by, timeout)
        self.s.rows = rows
        code, out = self.press()
        self.assertEqual(code, 200, out)
        self.assertLess(max(sizes), 3000, sizes)               # every query string well inside a 4 KB request line
        got = self.lines()
        self.assertEqual(got[("Wine", "Sold")][0], 404.0)      # the run's 4 wine sales and the 400 new ones
        self.assertEqual(got[("Wine", "Closing stock")][0], 3.0 + 400 * 5)

    def test_s5_only_a_draft_with_a_store_a_period_and_a_unit_is_worked_out(self):
        cases = [({"workflow_state": exr.FILED}, app.NOT_DRAFT), ({"store": ""}, app.NO_STORE),
                 ({"company": None}, app.NO_STORE), ({"unit": "Gallons"}, app.BAD_UNIT),
                 ({"to_date": "2026-09-30"}, "To is before From. Drop this return (Actions) and make a new one for the period."),
                 ({"from_date": None}, "Fill From and To, then save the return."),
                 ({"from_date": "2025-01-01", "to_date": "2026-01-02"}, "A return covers at most 366 days. Make one return a period.")]
        for change, words in cases:
            s = shop()
            s.returns[NAME].update(change)
            code, out = app.Service(CONF, s).handle("POST", "/exr/work", signed(body(), CONF["PP_WORK_SECRET"]), body())
            self.assertEqual((code, out["message"]["body"], out["message"]["level"], s.writes), (200, words, "warning", []),
                             change)

    def test_s5b_no_figures_while_the_lock_is_off(self):
        for rules in ([], [dict(self.s.rules[0], enabled=0)], [dict(self.s.rules[0], mode="flag")]):
            s = shop()
            s.rules = rules
            code, out = app.Service(CONF, s).handle("POST", "/exr/work", signed(body(), CONF["PP_WORK_SECRET"]), body())
            self.assertEqual((code, out["message"]["body"], s.writes),
                             (200, app.LOCK_OFF.format(exr.LOCK_RULE), []), rules)
            self.assertNotIn("Stock Ledger Entry", [r[1] for r in s.reads])

    def test_s5c_a_cancelled_row_before_the_period_stays_out_and_a_row_at_its_first_second_is_in_it(self):
        self.s.move("VODKA", "2026-09-30 23:59:59", "Sales Invoice", "SINV-Y", -9, cancelled=1)   # cancelled, at the end
        self.s.move("BEER6", "2026-10-01 00:00:00", "Purchase Receipt", "PR-EDGE", 2)              # at the start: in it
        self.press()
        got = self.lines()
        self.assertEqual(got[("Spirits", "Opening stock")][0], 36.0)
        self.assertEqual((got[("Beer", "Opening stock")][0], got[("Beer", "Received from suppliers")][0]), (5.0, 5.0))

    def test_s6_a_return_saved_meanwhile_is_never_written_over(self):
        orig = self.s.rows

        def rows(*a, **k):                         # someone saves the return while the press reads the ledger
            if a[0] == "Stock Entry":
                self.s.returns[NAME]["modified"] = "m-someone"
            return orig(*a, **k)
        self.s.rows = rows
        code, out = self.press()
        self.assertEqual((code, out["message"]["body"], self.s.writes), (200, app.CHANGED, []))

    def test_s7_a_press_out_of_time_writes_nothing(self):
        ticks = iter([0.0] + [0.1] * 5 + [8.0] * 20)
        svc = app.Service(CONF, self.s, clock=lambda: next(ticks))
        raw = body()
        code, out = svc.handle("POST", "/exr/work", signed(raw, CONF["PP_WORK_SECRET"]), raw)
        self.assertEqual((code, self.s.writes), (502, []))
        self.assertIn("ran out of time", out["error"])

    def test_s7b_reads_done_but_the_time_gone_writes_nothing(self):
        svc = app.Service(CONF, self.s, clock=lambda: 8.0 if len(self.s.reads) >= 11 else 0.1)
        raw = body()
        code, out = svc.handle("POST", "/exr/work", signed(raw, CONF["PP_WORK_SECRET"]), raw)
        self.assertEqual((code, len(self.s.reads), self.s.writes), (502, 11, []))

    def test_s8_the_apps_user_refused_by_the_site_is_said_in_words(self):
        for refuse in ((403, "PermissionError"), (417, "PermissionError")):
            self.s.fail_on = ("Stock Ledger Entry",) + refuse
            code, out = self.press()
            self.assertEqual((code, out["message"]["body"], self.s.writes), (200, app.REFUSED, []), refuse)

    def test_s8b_another_417_is_not_called_a_rights_problem_and_a_long_timestamp_is_refused(self):
        self.s.fail_on = ("Item", 417, "DataError")
        code, out = self.press()
        self.assertEqual((code, self.s.writes), (502, []))
        raw = body()
        h = signed(raw, CONF["PP_WORK_SECRET"])
        h["X-iVendNext-Timestamp"] = "9" * 5000
        self.assertEqual(self.svc.handle("POST", "/exr/work", h, raw)[0], 401)

    def test_s9_a_missing_return_and_a_bad_body(self):
        code, out = self.press(name="EXR-R-99999")
        self.assertEqual((code, out["message"]["body"]), (200, app.GONE))
        for raw in (b"not json", json.dumps({"point": "desk_action/1", "context": {"v": 1, "records": []}}).encode(),
                    body(doctype="PP EXR Duty Class")):
            self.assertEqual(self.svc.handle("POST", "/exr/work", signed(raw, CONF["PP_WORK_SECRET"]), raw)[0], 400, raw)

    def test_s10_a_bad_signature_another_secret_and_an_old_stamp_are_refused(self):
        self.assertEqual(self.press(secret="nope")[0], 401)
        raw = body()
        self.assertEqual(self.svc.handle("POST", "/exr/work", signed(raw, CONF["PP_WORK_SECRET"], ts=time.time() - 900),
                                         raw)[0], 401)
        self.assertEqual((self.s.reads, self.s.writes), ([], []))

    def test_s11_health_unknown_paths_and_a_large_body(self):
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"ok": 1}))
        self.assertEqual(self.svc.handle("POST", "/exr/other", {}, b"{}")[0], 404)
        self.assertEqual(self.svc.handle("POST", "/exr/work", {}, b"x" * (exr.BODY_MAX + 1))[0], 413)

    def test_s12_an_items_litres_and_strength_are_read_at_the_press(self):
        self.press()
        next(i for i in self.s.items if i["name"] == "RUM")[ITEM + "ml"] = 700
        self.s.returns[NAME]["lines"] = []
        self.press()
        self.assertEqual(self.lines()[("Spirits", "Sold")], (10.0, 7.6, 2.99))
        self.assertNotIn("left out", self.s.returns[NAME]["summary"])


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(CONF, object())
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {p: (k, CONF[f"PP_{k.upper()}_SECRET"]) for p, k in app.ROUTES.items()}
        self.assertEqual(set(self.routes), set(app.ROUTES))     # every signed point route of the service

    def call(self, path, raw, secret, test=True):
        import base64, hashlib, hmac, time
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        return self.svc.handle("POST", path, h, raw)

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and refused
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
