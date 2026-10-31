"""S40's two Desk buttons against the stand-in shop: *Block these batches* on a recall notice and *Refresh* on an
expiry worklist. Each test's number is the scenario it proves (README, *What it does*).

    python3 -m unittest discover -s samples/s40_expiry_recall/tests -p 'test_*.py'
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fakeshop import DISP, FRONT, QUAR, FakeTenant, call, day, press_body, service  # noqa: E402

import app  # noqa: E402
import recall  # noqa: E402

NOTICE = "PP RCL Recall Notice"


def notice_fields(lots, cls="Class I", depth="", received="2026-10-22 08:00:00"):
    return {"name": "RCL-00001", "recall_class": cls, "depth": depth, "received_on": received, "start_by": None,
            "complete_by": None, "lots": [{"batch": b} for b in lots]}


class Recall(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.shop.put_own("Recall Notice", "RCL-00001", {"notice_ref": "PPB/RCL/2026/17", "recall_class": "Class I",
                                                          "status": "Open", "lots": []})
        self.svc = service(self.shop)

    def press(self, lots, **kw):
        return call(self.svc, "/press/block", press_body(NOTICE, "RCL-00001", notice_fields(lots, **kw)))

    def notice(self):
        return self.shop.get_own("Recall Notice", "RCL-00001")

    def test_r1_a_lot_with_an_expiry_is_blocked_with_the_row_as_read(self):
        code, out = self.press(["AMOX-A"])
        self.assertEqual(code, 200)
        self.assertEqual(self.shop.lots["AMOX-A"]["disabled"], 1)
        put = [w for w in self.shop.writes if w[1] == "Batch"]
        self.assertEqual(put, [("update", "Batch", "AMOX-A", {"disabled": 1, "modified": "2026-10-20 10:00:00.000001"})])
        self.assertEqual(out["message"]["level"], "success")
        self.assertTrue(out["refresh"])
        self.assertIn("Blocked 1 lot.", out["message"]["body"])

    def test_r2_a_lot_with_no_expiry_is_never_saved(self):
        """Saving it would make the shop write a guessed expiry (manufacturing date + shelf life)."""
        code, out = self.press(["AMOX-N", "AMOX-A"])
        self.assertEqual([w[2] for w in self.shop.writes if w[1] == "Batch"], ["AMOX-A"])
        self.assertEqual(self.shop.lots["AMOX-N"]["disabled"], 0)
        self.assertEqual(out["message"]["level"], "warning")
        rows = {r["batch"]: r["outcome"] for r in self.notice()["lots"]}
        self.assertEqual(rows["AMOX-N"], recall.OUTCOME_WORDS["no_expiry"])

    def test_r2b_a_lot_of_an_item_that_does_not_track_expiry_is_blocked(self):
        code, out = self.press(["SOAP-N"])
        self.assertEqual(self.shop.lots["SOAP-N"]["disabled"], 1)

    def test_r3_already_blocked_and_unknown_lots_are_named_and_not_written(self):
        code, out = self.press(["AMOX-B", "NOPE-1"])
        self.assertEqual([w for w in self.shop.writes if w[1] == "Batch"], [])
        self.assertEqual({r["batch"]: r["outcome"] for r in self.notice()["lots"]},
                         {"AMOX-B": "already blocked", "NOPE-1": "not found"})
        self.assertIn("1 already blocked. 1 not found.", out["message"]["body"])

    def test_r4_stock_found_per_store_from_the_ledger_never_a_pos_sales_own_bundle(self):
        self.press(["AMOX-A"])
        self.assertEqual({(r["store"], r["batch"]): r["qty"] for r in self.notice()["stock"]},
                         {(DISP, "AMOX-A"): 35, (FRONT, "AMOX-A"): 9})

    def test_r5_the_ledger_is_read_whatever_the_lot_state(self):
        """The shop's own lot read drops a disabled lot; the trace must not: a second press still finds the stock."""
        self.press(["AMOX-A"])
        self.press(["AMOX-A"])
        self.assertEqual(self.shop.lots["AMOX-A"]["disabled"], 1)
        self.assertEqual(len(self.notice()["stock"]), 2)
        self.assertEqual(sum(1 for w in self.shop.writes if w[1] == "Batch"), 1)

    def test_r6_customers_supplied_at_consumer_depth_a_till_sale_before_and_after_its_day_closes(self):
        self.press(["AMOX-A"])
        got = {(r["customer"], r["document"]): r["qty"] for r in self.notice()["customers"]}
        self.assertEqual(got, {("CUST-1", "POS-1"): 3, ("CUST-5", "SI-MERGED"): 3, ("CUST-2", "SI-2"): 2,
                               ("CUST-4", "DN-1"): 1})
        self.assertNotIn("CUST-3", {r["customer"] for r in self.notice()["customers"]})    # a cancelled sale

    def test_r6b_the_headline_counts_sales_and_customers(self):
        code, out = self.press(["AMOX-A"])
        self.assertIn("4 sales to 4 customers", out["message"]["body"])

    def test_r6c_no_store_progress_for_a_quarantine_store(self):
        self.shop.bundles.append({"name": "B13", "voucher_type": "Stock Entry", "voucher_no": "STE-3", "warehouse": QUAR,
                                  "docstatus": 1, "is_cancelled": 0, "entries": [{"batch_no": "AMOX-A", "qty": 5}]})
        self.press(["AMOX-A"])
        stores = {r["store"] for (d, _), r in self.shop.own.items() if d == "PP RCL Recall Store Progress"}
        self.assertNotIn(QUAR, stores)
        self.assertIn(QUAR, {r["store"] for r in self.notice()["stock"]})

    def test_r7_retail_depth_traces_no_customer(self):
        code, out = self.press(["AMOX-A"], cls="Class II")
        self.assertEqual(self.notice().get("customers", []), [])
        self.assertEqual(self.notice()["depth"], "Retail")
        self.assertIn("customers not traced at retail depth", out["message"]["body"])
        self.assertFalse([r for r in self.shop.reads if r[0] == "rows" and r[1] in recall.SALES])

    def test_r8_the_clock_fills_what_the_notice_left_blank_and_never_overwrites(self):
        self.press(["AMOX-A"])
        n = self.notice()
        self.assertEqual((n["start_by"], n["complete_by"]), ("2026-10-23 08:00:00", "2026-11-05 08:00:00"))
        self.assertEqual((n["status"], n["blocked_on"]), ("Blocked", "2026-10-22 09:00:00"))
        self.shop.get_own("Recall Notice", "RCL-00001").update({"complete_by": "2026-10-30 17:00:00"})
        self.press(["AMOX-A"])
        self.assertEqual(self.notice()["complete_by"], "2026-10-30 17:00:00")

    def test_r9_a_store_progress_per_store_and_a_stores_own_work_kept(self):
        self.press(["AMOX-A"])
        dt = "PP RCL Recall Store Progress"
        made = {r["store"]: r for (d, _), r in self.shop.own.items() if d == dt}
        self.assertEqual({s: (r["qty_found"], r["status"]) for s, r in made.items()},
                         {DISP: (35, "To do"), FRONT: (9, "To do")})
        made[FRONT].update({"status": "Done", "qty_quarantined": 9})
        self.shop.bundles.append({"name": "B12", "voucher_type": "Stock Entry", "voucher_no": "STE-2", "warehouse": FRONT,
                                  "docstatus": 1, "is_cancelled": 0, "entries": [{"batch_no": "AMOX-A", "qty": -9}]})
        self.press(["AMOX-A"])
        front = self.shop.own[(dt, f"RCL-00001--{FRONT}")]
        self.assertEqual((front["qty_found"], front["status"], front["qty_quarantined"]), (0, "Done", 9))
        self.assertEqual(sum(1 for w in self.shop.writes if w[0] == "create" and w[1] == dt), 2)

    def test_r10_a_lot_changed_meanwhile_is_reported_and_not_written_over(self):
        self.shop.stale_lot = "AMOX-A"
        code, out = self.press(["AMOX-A"])
        self.assertEqual(self.shop.lots["AMOX-A"]["disabled"], 0)
        self.assertEqual(self.notice()["lots"][0]["outcome"], recall.OUTCOME_WORDS["changed"])
        self.assertEqual(out["message"]["level"], "warning")

    def test_r11_no_settings_is_said_and_nothing_is_written(self):
        self.shop.settings = None
        code, out = self.press(["AMOX-A"])
        self.assertEqual(out["message"]["body"], app.NO_SETTINGS)
        self.assertEqual(self.shop.writes, [])

    def test_r12_the_apps_user_refused_is_said_in_words(self):
        self.shop.refuse = 403
        self.assertEqual(self.press(["AMOX-A"])[1]["message"]["body"], app.REFUSED)

    def test_r13_a_press_must_be_signed_with_the_buttons_own_secret(self):
        raw = press_body(NOTICE, "RCL-00001", notice_fields(["AMOX-A"]))
        for secret in ("s40-receipt", "nope"):
            self.assertEqual(call(self.svc, "/press/block", raw, secret)[0], 401)
        self.assertEqual(self.shop.writes, [])

    def test_r14_a_press_on_another_record_type_is_refused_and_one_with_no_lot_is_answered_in_words(self):
        self.assertEqual(call(self.svc, "/press/block", press_body("Batch", "AMOX-A", {}))[0], 400)
        code, out = call(self.svc, "/press/block", press_body(NOTICE, "RCL-00001", notice_fields([])))
        self.assertEqual((code, out["message"]["level"]), (200, "warning"))
        self.assertIn("Add the lots", out["message"]["body"])
        self.assertEqual(self.shop.reads, [])

    def test_r15_a_press_at_another_depth_never_wipes_customers_already_traced(self):
        self.press(["AMOX-A"])
        self.assertEqual(len(self.notice()["customers"]), 4)
        self.press(["AMOX-A"], cls="Class II")
        self.assertEqual(len(self.notice()["customers"]), 4)


class Worklist(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.shop.put_own("Expiry Worklist", "EXW-00001", {"store": None, "near": [], "no_expiry": []})
        self.svc = service(self.shop)

    def press(self, store=None, window=None):
        raw = press_body("PP RCL Expiry Worklist", "EXW-00001", {"name": "EXW-00001", "store": store, "window_days": window})
        return call(self.svc, "/press/worklist", raw)

    def doc(self):
        return self.shop.get_own("Expiry Worklist", "EXW-00001")

    def test_w1_lots_with_stock_inside_the_window_and_past_their_date(self):
        code, out = self.press()
        self.assertEqual(code, 200)
        got = [(r["batch"], r["store"], r["qty"], r["days_left"]) for r in self.doc()["near"]]
        self.assertEqual(got, [("TRAM-X", DISP, 4, -3), ("PARA-A", DISP, 20, 30)])
        self.assertEqual(self.doc()["window_days"], 90)

    def test_w2_a_narrower_window_and_one_store(self):
        self.press(window=10)
        self.assertEqual([r["batch"] for r in self.doc()["near"]], ["TRAM-X"])
        self.press(store=QUAR)
        self.assertEqual(self.doc()["near"], [])

    def test_w3_the_pharmacists_action_is_kept_across_a_refresh(self):
        self.press()
        self.shop.get_own("Expiry Worklist", "EXW-00001")["near"][1]["action"] = "Marked down"
        self.press()
        self.assertEqual({r["batch"]: r["action"] for r in self.doc()["near"]},
                         {"TRAM-X": "To check", "PARA-A": "Marked down"})

    def test_w4_medicine_lots_with_no_expiry_listed_and_others_not(self):
        self.press()
        self.assertEqual([(r["batch"], r["disabled"]) for r in self.doc()["no_expiry"]], [("AMOX-N", 0)])

    def test_w4b_a_no_expiry_lot_on_a_recall_notice_is_marked(self):
        self.shop.put_own("Recall Notice", "RCL-9", {"lots": [{"batch": "AMOX-N"}]})
        self.press()
        self.assertEqual([(r["batch"], r["recalled"]) for r in self.doc()["no_expiry"]], [("AMOX-N", 1)])

    def test_w5_a_disabled_lot_is_not_on_the_near_list(self):
        self.shop.lots["PARA-A"]["disabled"] = 1
        self.press()
        self.assertNotIn("PARA-A", [r["batch"] for r in self.doc()["near"]])


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        from fakeshop import SECRETS
        self.svc = app.Service({f"PP_SECRET_{k.upper()}": v for k, v in SECRETS.items()}, object())
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {p: (k, SECRETS[k]) for p, k in app.ROUTES.items()}
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
