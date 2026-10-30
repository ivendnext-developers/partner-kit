"""S61's service against a stand-in retailer (``fakeshop.py``): a press checked by its signature, *Work out the payout*
writing exactly the lines owed (till sales and Desk invoices, returns off, the till day's combined invoice and other
companies, drafts and later days left out, lines another payout holds left out, a sale cancelled after its payout taken
back once, at most 500 lines), and *Pay this payout* marking the payout paid only after every line is checked again.

    python3 -m unittest discover -s samples/s61_consignment_payouts/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import app  # noqa: E402
import consign  # noqa: E402
from fakeshop import FakeShop  # noqa: E402

CONF = {"PP_WORK_SECRET": "w-secret", "PP_PAY_SECRET": "p-secret", "PP_ADMIN_TOKEN": "t"}
ITEM = "pp_csg_"


def body(name="CSG-P-00001", user="back@shop.example", doctype=None):
    return json.dumps({"point": "desk_action/1", "context": {
        "v": 1, "action": "x", "label": "x", "user": user, "lang": "en", "inputs": {}, "idempotency_key": "k",
        "records": [{"doctype": doctype or consign.PAYOUT, "name": name, "fields": {"name": name}}]}}).encode()


def signed(raw, secret, ts=None):
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}


def shop():
    """Consignor C1 at 40% since 1 October, items A and B (B at 60% of its own), C1's sales, and one item of another consignor."""
    s = FakeShop()
    s.consignors = {"C1": {"share": 40, "since": "2026-10-01"}, "C2": {"share": 50, "since": "2026-10-01"}}
    s.items = [{"name": "A", "item_name": "Coat", ITEM + "consignor": "C1", ITEM + "share": 0},
               {"name": "B", "item_name": "Bag", ITEM + "consignor": "C1", ITEM + "share": 60},
               {"name": "Z", "item_name": "Lamp", ITEM + "consignor": "C2", ITEM + "share": 0}]
    s.sale("POS Invoice", "PSI-1", [("pl1", "A", 100.0), ("pl2", "Z", 80.0)], day="2026-10-02")
    s.sale("POS Invoice", "PSI-2", [("pl3", "B", 50.0)], day="2026-10-03")
    s.sale("POS Invoice", "PSI-R", [("pl4", "A", -25.0)], day="2026-10-04", is_return=1)
    s.sale("Sales Invoice", "SI-1", [("sl1", "A", 10.0)], day="2026-10-05")                      # a Desk invoice
    s.sale("Sales Invoice", "SI-CONS", [("sl2", "A", 100.0)], day="2026-10-02", consolidated=1)  # the till day's
    s.sale("POS Invoice", "PSI-OTHER", [("pl5", "A", 70.0)], company="Other Co")
    s.sale("POS Invoice", "PSI-DRAFT", [("pl6", "A", 70.0)], docstatus=0)
    s.sale("POS Invoice", "PSI-LATE", [("pl7", "A", 70.0)], day="2026-11-05")
    s.sale("POS Invoice", "PSI-EARLY", [("pl8", "A", 70.0)], day="2026-09-20")                # before Consigned since
    s.payout("CSG-P-00001")
    return s


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.s = shop()
        self.svc = app.Service(CONF, self.s)

    def tearDown(self):
        consign.use_prefix("PP CSG")

    def press(self, sub="work", name="CSG-P-00001", secret=None, user="back@shop.example"):
        raw = body(name, user)
        return self.svc.handle("POST", f"/csg/{sub}", signed(raw, secret or CONF[f"PP_{sub.upper()}_SECRET"]), raw)

    def paid_ready(self, name="CSG-P-00001"):
        self.s.payouts[name].update(paid_with="Cash", paid_on="2026-10-31")

    def lines(self, name="CSG-P-00001"):
        return {r["sale_line"]: (r["kind"], round(r["sale_amount"], 2), r["share"], round(r["payout"], 2))
                for r in self.s.payouts[name]["lines"]}

    def test_s1_work_out_writes_the_owed_lines_and_totals(self):
        code, out = self.press()
        self.assertEqual(code, 200, out)
        self.assertEqual(self.lines(), {
            "pl1": ("Sale", 100.0, 40, 40.0),                 # a till sale at the consignor's 40%
            "pl3": ("Sale", 50.0, 60, 30.0),                  # the item's own 60%
            "pl4": ("Return", -25.0, 40, -10.0),              # a till return, negative
            "sl1": ("Sale", 10.0, 40, 4.0)})                  # a Desk invoice
        p = self.s.payouts["CSG-P-00001"]
        self.assertEqual((p["sales_total"], p["payout_total"], p["worked_out_by"]), (135.0, 64.0, "back@shop.example"))
        self.assertIn("4 lines: 3 sales, 1 return. Sold for 135.00 USD; the consignor's share 64.00 USD.", p["summary"])
        self.assertEqual(out["message"]["body"], p["summary"])
        self.assertTrue(out["refresh"])
        self.assertEqual([r["sale_line"] for r in p["lines"]], ["pl1", "pl3", "pl4", "sl1"])   # oldest first

    def test_s2_the_reads_ask_only_for_the_consignors_items_and_submitted_or_cancelled_sales(self):
        self.press()
        heads = [r for r in self.s.reads if r[0] == "rows" and r[1] in ("POS Invoice", "Sales Invoice")]
        self.assertEqual({r[1] for r in heads}, {"POS Invoice", "Sales Invoice"})
        self.assertIn("is_consolidated", next(r for r in heads if r[1] == "Sales Invoice")[2])
        self.assertNotIn(("rows", consign.CONSIGNOR, ("name", "consignor_name", "phone", "email"), None), self.s.reads)
        self.assertIn(("rows", consign.CONSIGNOR, ("name", "share", "since"), None), self.s.reads)   # never the name or contact

    def test_s3_a_line_another_payout_holds_is_left_and_a_cancelled_payouts_is_taken(self):
        self.s.payout("CSG-P-00010", consignor="C2", lines=[{"sale_line": "pl1", "sale_type": "POS Invoice", "payout": 40}])
        self.s.payout("CSG-P-00011", state=consign.CANCELLED, lines=[{"sale_line": "pl3", "sale_type": "POS Invoice", "payout": 30}])
        self.press()
        self.assertEqual(sorted(self.lines()), ["pl3", "pl4", "sl1"])     # held by another consignor's draft: left

    def test_s4_pay_marks_it_paid_once_every_line_is_checked(self):
        self.press()
        self.paid_ready()
        n = len(self.s.writes)
        code, out = self.press("pay", user="boss@shop.example")
        self.assertEqual(code, 200)
        self.assertIn("Paid: 64.00 USD", out["message"]["body"])
        self.assertEqual(self.s.writes[n:], [(consign.PAYOUT, "CSG-P-00001", {"workflow_state": consign.PAID,
                                                                       "paid_by": "boss@shop.example"})])
        self.s.payout("CSG-P-00002")
        self.press(name="CSG-P-00002")
        self.assertEqual(self.lines("CSG-P-00002"), {})                       # nothing is ever paid twice
        self.assertIn("Nothing owed", self.s.payouts["CSG-P-00002"]["summary"])

    def test_s5_pay_refuses_without_how_and_when_it_was_paid(self):
        self.press()
        for fill in ({}, {"paid_with": "Cash"}, {"paid_on": "2026-10-31"}):
            self.s.payouts["CSG-P-00001"].update(dict({"paid_with": None, "paid_on": None}, **fill))
            n = len(self.s.writes)
            out = self.press("pay")[1]
            self.assertIn("Fill Paid with and Paid on first", out["message"]["body"])
            self.assertEqual(len(self.s.writes), n)

    def test_s6_pay_refuses_while_the_lock_is_off(self):
        self.press()
        self.paid_ready()
        for rule in ({"enabled": 0, "mode": "refuse"}, {"enabled": 1, "mode": "flag"}, None):
            self.s.rules = [dict({"name": "R1", "rule_name": consign.LOCK_RULE}, **rule)] if rule else []
            out = self.press("pay")[1]
            self.assertIn(f"Switch on the rule {consign.LOCK_RULE}", out["message"]["body"], rule)
        self.assertEqual(self.s.payouts["CSG-P-00001"]["workflow_state"], consign.DRAFT)

    def test_s7_pay_refuses_a_line_edited_by_hand_or_a_total_that_is_not_the_sum(self):
        self.press()
        self.paid_ready()
        base = json.loads(json.dumps(self.s.payouts["CSG-P-00001"]))
        for field, value, words in (("payout", 99.0, "A line has changed"), ("share", 90, "A line has changed"),
                                    ("kind", "Return", "A line has changed"), ("sale_line", "zz", "no longer owed")):
            self.s.payouts["CSG-P-00001"] = json.loads(json.dumps(base))
            self.s.payouts["CSG-P-00001"]["lines"][0][field] = value
            self.assertIn(words, self.press("pay")[1]["message"]["body"], field)
        self.s.payouts["CSG-P-00001"] = json.loads(json.dumps(base))
        self.s.payouts["CSG-P-00001"]["payout_total"] = 65.0
        self.assertIn("not the sums of its lines", self.press("pay")[1]["message"]["body"])
        self.s.payouts["CSG-P-00001"] = json.loads(json.dumps(base))
        self.s.payouts["CSG-P-00001"]["sales_total"] = 999.0
        self.assertIn("not the sums of its lines", self.press("pay")[1]["message"]["body"])
        self.s.payouts["CSG-P-00001"] = json.loads(json.dumps(base))
        self.s.payouts["CSG-P-00001"]["lines"].append(dict(base["lines"][0]))
        self.assertIn("on this payout twice", self.press("pay")[1]["message"]["body"])
        self.assertEqual(self.s.payouts["CSG-P-00001"]["workflow_state"], consign.DRAFT)

    def test_s8_a_copied_payout_refuses_both_pays_until_one_is_dropped(self):
        self.press()
        self.paid_ready()
        self.s.payout("CSG-P-00001-copy", lines=self.s.payouts["CSG-P-00001"]["lines"], payout_total=64.0, sales_total=135.0,
                      paid_with="Cash", paid_on="2026-10-31")
        for name, other in (("CSG-P-00001", "CSG-P-00001-copy"), ("CSG-P-00001-copy", "CSG-P-00001")):
            self.assertIn(f"Payout {other} for this consignor is still a draft", self.press("pay", name=name)[1]["message"]["body"])
        self.s.payouts["CSG-P-00001-copy"]["workflow_state"] = consign.CANCELLED      # Drop
        self.assertIn("Paid:", self.press("pay")[1]["message"]["body"])

    def test_s9_a_paid_payout_cancelled_frees_its_lines(self):
        self.press()
        self.paid_ready()
        self.press("pay")
        self.s.payouts["CSG-P-00001"]["workflow_state"] = consign.CANCELLED      # the workflow's Cancel, Accounts Manager
        self.s.payout("CSG-P-00002")
        self.press(name="CSG-P-00002")
        self.assertEqual(sorted(self.lines("CSG-P-00002")), ["pl1", "pl3", "pl4", "sl1"])

    def test_s10_a_sale_cancelled_after_its_payout_was_paid_is_taken_back_once(self):
        self.press()
        self.paid_ready()
        self.press("pay")
        next(h for h in self.s.heads["POS Invoice"] if h["name"] == "PSI-2")["docstatus"] = 2
        self.s.payout("CSG-P-00002")
        self.press(name="CSG-P-00002")
        self.assertEqual(self.lines("CSG-P-00002"), {"pl3/1": ("Taken back", -50.0, 60, -30.0)})
        self.assertEqual(self.s.payouts["CSG-P-00002"]["payout_total"], -30.0)
        self.assertTrue(self.s.payouts["CSG-P-00002"]["summary"].startswith("1 line: 1 paid sale taken back. Sold for -50.00"))
        self.assertIn("set Sales up to later and work it out again", self.s.payouts["CSG-P-00002"]["summary"])
        self.s.payouts["CSG-P-00002"].update(paid_with="Cash", paid_on="2026-10-31")
        self.assertIn("returns are more than the sales", self.press("pay", name="CSG-P-00002")[1]["message"]["body"])
        self.s.payout("CSG-P-00003")                                             # one draft a consignor
        self.assertIn("Payout CSG-P-00002 for this consignor is still a draft", self.press(name="CSG-P-00003")[1]["message"]["body"])
        self.assertEqual(self.lines("CSG-P-00003"), {})

    def test_s21_a_take_back_paid_then_its_payout_cancelled_is_corrected_once(self):
        self.press()
        self.paid_ready()
        self.press("pay")                                                        # 00001 pays pl3 (30)
        next(h for h in self.s.heads["POS Invoice"] if h["name"] == "PSI-2")["docstatus"] = 2
        self.s.sale("POS Invoice", "PSI-NEW", [("pl9", "B", 100.0)], day="2026-10-20")
        self.s.payout("CSG-P-00002")
        self.press(name="CSG-P-00002")                                           # the take-back and a new sale
        self.assertEqual(self.lines("CSG-P-00002"), {"pl3/1": ("Taken back", -50.0, 60, -30.0), "pl9": ("Sale", 100.0, 60, 60.0)})
        self.s.payouts["CSG-P-00002"].update(paid_with="Cash", paid_on="2026-10-31")
        self.assertIn("Paid:", self.press("pay", name="CSG-P-00002")[1]["message"]["body"])
        self.s.payouts["CSG-P-00001"]["workflow_state"] = consign.CANCELLED      # 00001 was never really paid
        self.s.payout("CSG-P-00003")
        self.press(name="CSG-P-00003")
        self.assertEqual(self.lines("CSG-P-00003"), {"pl1": ("Sale", 100.0, 40, 40.0), "pl4": ("Return", -25.0, 40, -10.0),
                                                     "sl1": ("Sale", 10.0, 40, 4.0),
                                                     "pl3/1": ("Correction", 50.0, 60, 30.0)})   # the -30 given back

    def test_s22_after_an_item_moves_its_paid_sale_is_taken_back_from_the_consignor_who_was_paid(self):
        self.press()
        self.paid_ready()
        self.press("pay")                                                        # C1 paid 30 on the bag (pl3)
        self.s.items[1][ITEM + "consignor"] = "C2"
        next(h for h in self.s.heads["POS Invoice"] if h["name"] == "PSI-2")["docstatus"] = 2
        self.s.payout("CSG-P-00007", consignor="C2")
        self.press(name="CSG-P-00007")
        self.assertEqual(self.lines("CSG-P-00007"), {"pl2": ("Sale", 80.0, 50, 40.0)})   # C2's lamp only: never the bag's
        self.s.payout("CSG-P-00008")
        self.press(name="CSG-P-00008")
        self.assertEqual(self.lines("CSG-P-00008"), {"pl3/1": ("Taken back", -50.0, 60, -30.0)})

    def test_s23_a_paid_line_moved_to_another_consignor_is_never_paid_again(self):
        self.press()
        self.paid_ready()
        self.press("pay")
        self.s.items[1][ITEM + "consignor"] = "C2"
        self.s.payout("CSG-P-00007", consignor="C2")
        self.press(name="CSG-P-00007")
        self.assertEqual(self.lines("CSG-P-00007"), {"pl2": ("Sale", 80.0, 50, 40.0)})   # the bag's pl3 is on C1's paid payout

    def test_s11_a_sale_cancelled_before_pay_stops_the_pay(self):
        self.press()
        self.paid_ready()
        next(h for h in self.s.heads["POS Invoice"] if h["name"] == "PSI-2")["docstatus"] = 2
        self.assertIn("no longer owed", self.press("pay")[1]["message"]["body"])

    def test_s12_at_most_500_lines_oldest_first_and_the_rest_wait(self):
        s = self.s
        s.items.append({"name": "M", "item_name": "Many", ITEM + "consignor": "C1", ITEM + "share": 0})
        for i in range(501):
            s.sale("POS Invoice", f"PSI-M{i:03}", [(f"m{i:03}", "M", 1.0)], day="2026-10-01")
        self.press()
        rows = s.payouts["CSG-P-00001"]["lines"]
        self.assertEqual(len(rows), 500)
        self.assertEqual(rows[0]["sale_line"], "m000")
        self.assertIn("5 more lines wait for the next payout", s.payouts["CSG-P-00001"]["summary"])

    def test_s24_pay_refuses_a_line_another_consignors_payout_took_meanwhile(self):
        self.press()
        self.paid_ready()
        self.s.payout("CSG-P-00012", consignor="C2", lines=[{"sale_line": "pl1", "sale_type": "POS Invoice", "payout": 40}])
        self.assertIn("also on payout CSG-P-00012", self.press("pay")[1]["message"]["body"])
        self.assertEqual(self.s.payouts["CSG-P-00001"]["workflow_state"], consign.DRAFT)

    def test_s13_only_a_draft_and_only_with_a_consignor(self):
        self.s.payouts["CSG-P-00001"]["workflow_state"] = consign.PAID
        self.assertIn("Only a draft payout", self.press()[1]["message"]["body"])
        self.s.payout("CSG-P-00004", consignor="")
        self.assertIn("Choose the consignor", self.press(name="CSG-P-00004")[1]["message"]["body"])
        del self.s.payouts["CSG-P-00004"]
        self.s.consignors["C1"]["share"] = 0
        self.s.payout("CSG-P-00005")
        self.assertIn("has no share yet", self.press(name="CSG-P-00005")[1]["message"]["body"])
        self.s.consignors["C1"]["share"] = 40
        self.s.items[0][ITEM + "share"] = 120
        self.assertIn("on item A must be a percent", self.press(name="CSG-P-00005")[1]["message"]["body"])
        self.assertEqual(self.s.writes, [])

    def test_s14_the_apps_user_refused_by_the_site_is_said_in_words(self):
        for status, kind in ((401, "AuthenticationError"), (403, "PermissionError"), (417, "PermissionError"),
                             (417, "WorkflowPermissionError")):
            self.s.refuse = (status, kind)
            code, out = self.press()
            self.assertEqual(code, 200)
            self.assertIn("may not read the sales and items", out["message"]["body"])

    def test_s14b_another_417_is_not_called_a_rights_problem_and_a_long_timestamp_is_refused(self):
        self.s.refuse = (417, "ValidationError")
        self.assertEqual(self.press()[0], 502)
        raw = body()
        h = {"X-iVendNext-Timestamp": "9" * 5000, "X-iVendNext-Signature": "x"}
        self.assertEqual(self.svc.handle("POST", "/csg/work", h, raw)[0], 401)

    def test_s15_an_edit_meanwhile_is_never_written_over(self):
        real = self.s.update

        def edited(doctype, name, b):
            self.s.payouts[name]["modified"] = "someone-else"
            return real(doctype, name, b)
        self.s.update = edited
        self.assertIn("changed while this press read it", self.press()[1]["message"]["body"])
        self.assertEqual(self.s.writes, [])

    def test_s16_out_of_time_writes_nothing(self):
        t = [0.0]

        def clock():
            t[0] += 1.0                  # each read takes a second: past the budget before the write
            return t[0]
        self.svc.clock = clock
        code, out = self.press()
        self.assertEqual(code, 502)
        self.assertEqual(self.s.writes, [])

    def test_s17_each_button_takes_only_its_own_secret_and_a_bad_signature_is_refused(self):
        self.assertEqual(self.press("work", secret="p-secret")[0], 401)
        self.assertEqual(self.press("pay", secret="w-secret")[0], 401)
        raw = body()
        h = signed(raw, "w-secret", ts=time.time() - 1000)
        self.assertEqual(self.svc.handle("POST", "/csg/work", h, raw)[0], 401)
        self.assertEqual(self.s.reads, [])

    def test_s18_another_record_type_or_two_payouts_are_refused_before_any_read(self):
        for raw in (body(doctype="Item"), json.dumps({"point": "desk_action/1", "context": {"v": 1, "records": [
                {"doctype": consign.PAYOUT, "name": "CSG-P-00001"}, {"doctype": consign.PAYOUT, "name": "CSG-P-00002"}]}}).encode()):
            self.assertEqual(self.svc.handle("POST", "/csg/work", signed(raw, "w-secret"), raw)[0], 400)
        self.assertEqual(self.s.reads, [])

    def test_s19_a_missing_payout_is_said_in_words(self):
        self.assertIn("not found", self.press(name="NOPE")[1]["message"]["body"])

    def test_s20_health_and_unknown_routes(self):
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"ok": 1}))
        self.assertEqual(self.svc.handle("POST", "/csg/other", {}, b"{}")[0], 404)


if __name__ == "__main__":
    unittest.main()
