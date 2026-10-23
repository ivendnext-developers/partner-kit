"""S43's service against a stand-in shop: the payer door's two calls, claims from the feed's booked sales and returns,
the claims file, a remittance, the bill-back, and every refusal (a bad signature, a down shop, another customer's
member).

    python3 -m unittest discover -s samples/s43_third_party_payer/tests -p 'test_*.py'
"""

import base64
import csv
import hashlib
import hmac
import io
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [os.path.join(SAMPLE, "service"), SAMPLE, HERE]
import app  # noqa: E402
from fake_shop import FakeShop  # noqa: E402

SECRETS = {k: f"s-{k}" for k in ("payer", "claims", "file", "remit", "billback")}
NOW = time.mktime((2026, 10, 23, 12, 0, 0, 0, 0, -1))


def conf(**kw):
    c = {f"IVN_SECRET_{k.upper()}": v for k, v in SECRETS.items()}
    c.update(IVN_SHOP_URL="https://shop.example", IVN_SHOP_KEY="k:s")
    c.update(kw)
    return c


def signed(body, key, ts=None, secret=None):
    raw = json.dumps(body).encode()
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new((SECRETS[key] if secret is None else secret).encode(), ts.encode() + b"." + raw,
                                    hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw


def press(record, name):
    return {"point": "desk_action/1", "context": {"v": 1, "records": [{"doctype": record, "name": name}]}}


LINES = [{"line_id": "r1", "item_code": "PHD-AMOX-500", "qty": 2, "uom": "Nos", "amount": 240, "discount": 0},
         {"line_id": "r2", "item_code": "PHD-PARA-500", "qty": 2, "uom": "Nos", "amount": 50, "discount": 0}]


class Base(unittest.TestCase):
    def setUp(self):
        self.shop = FakeShop().generic()
        self.svc = app.Service(conf(), api=self.shop, now=lambda: NOW)

    def call(self, path, body, key, **kw):
        headers, raw = signed(body, key, **kw)
        return self.svc.handle("POST", path, headers, raw)

    def payer(self, body):
        return self.call("/icp/payer", dict({"contract": "payer/1"}, **body), "payer")

    def coverage(self, **kw):
        body = {"call": "coverage", "sale_ref": "PHD-26-0001", "customer": "C1", "member": "m1", "date": "2026-10-23",
                "precision": 2, "lines": [dict(l) for l in LINES]}
        body.update(kw)
        return self.payer(body)


class Calls(Base):
    def test_covers_lists_the_customers_cover_with_the_member_number_masked(self):
        code, out = self.payer({"call": "covers", "customer": "C1", "date": "2026-10-23"})
        self.assertEqual(code, 200)
        self.assertEqual(out["covers"][0] | {}, {"member": "m1", "payer": "GEN-INS", "payer_title": "Generic Insurer",
                                                 "payer_customer": "Generic Insurer", "plan": "Generic Silver",
                                                 "plan_title": "Generic Silver", "member_label": "…0123",
                                                 "valid_to": "2026-12-31", "price_list": "Generic Insurer Prices",
                                                 "promotions_apply": 1})
        self.assertNotIn("GEN-000123", json.dumps(out))

    def test_a_barred_customer_has_no_cover(self):
        code, out = self.payer({"call": "covers", "customer": "C2", "date": "2026-10-23"})
        self.assertEqual((code, out["covers"], out["refused"]["code"]), (200, [], "barred"))

    def test_coverage_answers_the_contract(self):
        code, out = self.coverage()
        self.assertEqual((code, out["contract"], out["answer"], out["claim_ref"]),
                         (200, "payer/1", "cover", "GEN-INS-PHD-26-0001"))
        self.assertEqual((out["totals"]["payer_share"], out["totals"]["patient_share"]), ("228.80", "61.20"))
        for l in out["lines"]:
            self.assertEqual(set(l) >= {"line_id", "covered", "sellable", "payer_share", "patient_share",
                                        "covered_qty", "qty_limit", "reason"}, True)

    def test_an_item_off_the_insurers_list_is_not_sellable_on_the_cover(self):
        code, out = self.coverage(lines=LINES + [{"line_id": "r3", "item_code": "PHD-VITC", "qty": 1, "amount": 30}])
        self.assertEqual((out["answer"], out["lines"][2]["reason"]), ("refuse", "not_on_list"))

    def test_an_item_at_zero_on_the_list_is_not_sellable_whatever_the_line_says(self):
        code, out = self.coverage(lines=[{"line_id": "r1", "item_code": "PHD-TRAM-50", "qty": 1, "amount": 180}])
        self.assertEqual((out["answer"], out["lines"][0]["reason"]), ("refuse", "zero_on_list"))

    def test_a_list_row_counts_only_as_the_engine_applies_it(self):
        # the plan's list carries the item only in another unit, for another customer, or for a batch: not listed
        for extra in ({"uom": "Box"}, {"customer": "C9"}, {"batch_no": "LOT-1"}):
            self.shop.tables["Item Price"] = [dict({"item_code": "PHD-AMOX-500", "price_list": "Generic Insurer Prices",
                                                    "price_list_rate": 120}, **extra)]
            out = self.coverage(lines=[dict(LINES[0])])[1]
            self.assertEqual((out["answer"], out["lines"][0]["reason"]), ("refuse", "not_on_list"), extra)
        self.shop.tables["Item Price"] = [{"item_code": "PHD-AMOX-500", "price_list": "Generic Insurer Prices",
                                           "price_list_rate": 120, "customer": "C1"}]
        self.assertEqual(self.coverage(lines=[dict(LINES[0])])[1]["answer"], "cover")   # this customer's own row

    def test_two_lines_of_one_item_in_two_units_are_judged_each_on_its_own_unit(self):
        self.shop.tables["Item Price"] = [{"item_code": "PHD-AMOX-500", "price_list": "Generic Insurer Prices",
                                           "uom": "Nos", "price_list_rate": 120},
                                          {"item_code": "PHD-AMOX-500", "price_list": "Generic Insurer Prices",
                                           "uom": "Box", "price_list_rate": 0}]
        out = self.coverage(lines=[dict(LINES[0]), dict(LINES[0], line_id="r9", uom="Box", amount=1200)])[1]
        self.assertEqual([l["reason"] for l in out["lines"]], [None, "zero_on_list"])

    def test_a_line_not_at_the_sales_precision_or_a_repeated_line_id_is_refused(self):
        self.assertEqual(self.coverage(lines=[dict(LINES[0], amount=33.333)])[0], 400)
        self.assertEqual(self.coverage(lines=[dict(LINES[0]), dict(LINES[1], line_id="r1")])[0], 400)

    def test_a_slow_shop_answers_503_before_the_doors_five_seconds(self):
        slow = self.shop.get_one
        self.shop.get_one = lambda *a: (time.sleep(0.05), slow(*a))[1]
        keep, app.ANSWER_BY = app.ANSWER_BY, 0.01
        try:
            self.assertEqual(self.coverage()[0], 503)
        finally:
            app.ANSWER_BY = keep

    def test_the_item_group_is_read_from_the_shop_when_the_door_does_not_send_it(self):
        out = self.coverage()[1]
        self.assertEqual(out["lines"][1]["extra_pay"], "4.00")       # OTC: 2 a unit, by its item group

    def test_another_customers_member_reference_is_no_cover(self):
        out = self.coverage(member="m2")[1]
        self.assertEqual((out["answer"], out["code"]), ("no_cover", "no_member"))

    def test_a_bad_signature_an_old_one_and_a_wrong_route_secret_are_refused(self):
        body = {"contract": "payer/1", "call": "covers", "customer": "C1"}
        self.assertEqual(self.call("/icp/payer", body, "payer", secret="nope")[0], 401)
        self.assertEqual(self.call("/icp/payer", body, "payer", ts=time.time() - 3600)[0], 401)
        self.assertEqual(self.call("/icp/payer", body, "claims")[0], 401)      # another subscription's secret

    def test_a_route_whose_secret_is_not_set_refuses_every_call(self):
        self.svc = app.Service(conf(IVN_SECRET_PAYER=""), api=self.shop)
        body = {"contract": "payer/1", "call": "covers", "customer": "C1"}
        self.assertEqual(self.call("/icp/payer", body, "payer", secret="")[0], 401)   # signed with the empty secret

    def test_a_shop_that_is_down_answers_503_and_the_door_says_no_cover(self):
        self.shop.fail = True
        self.assertEqual(self.coverage()[0], 503)

    def test_a_call_that_is_not_payer_1_is_refused(self):
        self.assertEqual(self.call("/icp/payer", {"contract": "check/1"}, "payer")[0], 400)
        self.assertEqual(self.payer({"call": "coverage", "customer": "C1", "lines": []})[0], 400)

    def test_health(self):
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"status": "ok"}))


def door_lines(answer):
    return [{"name": l["line_id"], "item_code": l["item_code"], "qty": float(l["covered_qty"]), "stock_qty":
             float(l["covered_qty"]), "uom": "Nos", "barcode": "0612345678901", "warehouse": "Pharmacy Dispensary",
             "payer_share": l["payer_share"], "patient_share": l["patient_share"],
             "payer_covered_qty": float(l["covered_qty"])} for l in answer["lines"]]


class Claims(Base):
    def booked(self, name="PHD-26-0001"):
        out = self.coverage(sale_ref=name)[1]
        return self.shop.book(name, door_lines(out))

    def build(self):
        return self.call("/icp/press/claims", press("PP ICP Payer", "GEN-INS"), "claims")

    def test_a_booked_sale_becomes_a_ready_claim_once(self):
        self.booked()
        code, out = self.build()
        self.assertEqual((code, out["message"]["body"]), (200, "1 claims made, 0 reduced by returns, 0 failed."))
        c = self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0001")
        self.assertEqual((c["status"], c["payer_share"], c["member_number"], c["prescription"]),
                         ("Ready", "228.80", "GEN-000123", "RX-77"))
        self.shop.done.clear()                                    # the feed sends it again: the claim's name holds
        self.assertEqual(self.build()[1]["message"]["body"], "0 claims made, 0 reduced by returns, 0 failed.")
        self.assertEqual(len(self.shop.rows("PP ICP Claim")), 1)

    def test_two_sales_under_one_claim_reference_fail_loudly_never_silently(self):
        self.booked("S-1")
        self.shop.book("S-2", [], payer_claim_ref="GEN-INS-S-1")
        self.assertEqual(self.build()[1]["message"]["body"], "1 claims made, 0 reduced by returns, 1 failed.")

    def test_the_tills_own_posting_of_a_payer_sale_is_never_a_second_claim(self):
        self.booked("S-1")
        self.shop.book("SINV-1", [{"name": "x", "item_code": "PHD-AMOX-500", "pos_invoice": "S-1"}],
                       doctype="Sales Invoice", payer_claim_ref="GEN-INS-S-1")
        self.assertEqual(self.build()[1]["message"]["body"], "1 claims made, 0 reduced by returns, 0 failed.")

    def test_a_return_before_its_claim_is_tried_again_never_dropped(self):
        out = self.coverage(sale_ref="S-1")[1]
        self.shop.book("S-1-RET", [{"name": "x1", "item_code": "PHD-PARA-500", "qty": -2, "pos_invoice_item": "r2",
                                    "payer_back": "45.60"}], is_return=1, payer_claim_ref=out["claim_ref"])
        self.assertIn("1 failed", self.build()[1]["message"]["body"])
        self.shop.book("S-1", door_lines(out))
        self.shop.events.append(self.shop.events.pop(0))            # the failed return comes back after its sale
        self.build()
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-S-1")["payer_share"], "183.20")

    def test_several_remittance_lines_for_one_claim_are_summed_before_it_is_settled(self):
        self.booked("S-1")
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="REM-9", payer="GEN-INS", lines=[
            {"name": "a", "claim_ref": "GEN-INS-S-1", "paid": "120"},
            {"name": "b", "claim_ref": "GEN-INS-S-1", "paid": "108.80"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "REM-9"), "remit")
        c = self.shop.find("PP ICP Claim", "GEN-INS-S-1")
        self.assertEqual((c["status"], c["received"]), ("Paid", "228.80"))
        self.assertEqual({r["result"] for r in self.shop.find("PP ICP Remittance", "REM-9")["lines"]}, {"Paid"})

    def test_a_later_part_payment_of_a_short_claim_is_kept(self):
        self.booked("S-1")
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        for i, paid in enumerate(("100", "50", "78.80")):
            self.shop.add("PP ICP Remittance", name=f"R{i}", payer="GEN-INS",
                          lines=[{"name": f"l{i}", "claim_ref": "GEN-INS-S-1", "paid": paid}])
            self.call("/icp/press/remit", press("PP ICP Remittance", f"R{i}"), "remit")
        c = self.shop.find("PP ICP Claim", "GEN-INS-S-1")
        self.assertEqual((c["status"], c["received"]), ("Paid", "228.80"))

    def test_a_door_that_books_nothing_leaves_the_claim_unchanged(self):
        self.booked("S-1")
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="R", payer="GEN-INS",
                      lines=[{"name": "l", "claim_ref": "GEN-INS-S-1", "paid": "0", "rejected": 1, "reason": "x"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "R"), "remit")
        self.shop.bill_back = lambda *a: {}
        out = self.call("/icp/press/billback", press("PP ICP Claim", "GEN-INS-S-1"), "billback")[1]
        self.assertEqual(out["message"]["level"], "warning")
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-S-1")["status"], "Rejected")

    def test_a_sale_with_no_payer_leg_or_another_payers_is_not_ours(self):
        self.shop.book("CASH-1", [], payer_claim_ref=None, payer_code=None)
        self.shop.book("OTHER-1", [], payer_code="SOMEONE-ELSE")
        self.build()
        self.assertEqual(self.shop.rows("PP ICP Claim"), [])
        self.assertEqual(len(self.shop.done), 2)

    def test_a_return_reduces_its_claim_once(self):
        self.booked()
        self.build()
        self.shop.book("PHD-26-0001-RET", [{"name": "x1", "item_code": "PHD-PARA-500", "qty": -2,
                                             "pos_invoice_item": "r2", "payer_back": "-45.60"}],
                       is_return=1, return_against="PHD-26-0001", payer_claim_ref="GEN-INS-PHD-26-0001")
        self.build()
        self.shop.done.clear()
        self.build()                                              # the same return again: reduced once
        c = self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0001")
        self.assertEqual((c["payer_share"], c["returns"]), ("183.20", "PHD-26-0001-RET"))

    def test_the_claims_file_puts_ready_claims_in_one_batch_and_marks_them_sent(self):
        self.booked()
        self.booked("PHD-26-0002")
        self.build()
        code, out = self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.assertIn("2 claims in", out["message"]["body"])
        batch = self.shop.rows("PP ICP Claim Batch")[0]
        rows = list(csv.DictReader(io.StringIO(batch["csv"])))
        self.assertEqual(len(rows), 4)
        self.assertEqual({c["status"] for c in self.shop.rows("PP ICP Claim")}, {"Submitted"})
        code, out = self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.assertEqual(out["message"]["body"], "No claim of Generic Insurer is ready.")

    def test_a_remittance_pays_shorts_and_rejects_claims(self):
        for n in ("A", "B", "C"):
            self.booked(n)
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="REM-1", payer="GEN-INS", lines=[
            {"name": "l1", "claim_ref": "GEN-INS-A", "paid": "228.80"},
            {"name": "l2", "claim_ref": "GEN-INS-B", "paid": "200"},
            {"name": "l3", "claim_ref": "GEN-INS-C", "paid": "0", "rejected": 1, "reason": "card expired"},
            {"name": "l4", "claim_ref": "GEN-INS-Z", "paid": "10"},
            {"name": "l5", "claim_ref": "OTHER-1", "paid": "50"}])
        self.shop.add("PP ICP Claim", name="OTHER-1", claim_ref="OTHER-1", payer="OTHER", status="Submitted",
                      payer_share="50", lines=[])
        code, out = self.call("/icp/press/remit", press("PP ICP Remittance", "REM-1"), "remit")
        self.assertEqual(out["message"]["body"], "3 of 5 lines matched.")
        self.assertEqual(self.shop.find("PP ICP Claim", "OTHER-1")["status"], "Submitted")
        st = {c["name"]: (c["status"], c.get("received")) for c in self.shop.rows("PP ICP Claim") if c["payer"] == "GEN-INS"}
        self.assertEqual(st, {"GEN-INS-A": ("Paid", "228.80"), "GEN-INS-B": ("Short paid", "200"),
                              "GEN-INS-C": ("Rejected", "0")})
        r = self.shop.find("PP ICP Remittance", "REM-1")
        self.assertEqual(r["status"], "Partly matched")
        self.assertEqual([l["result"] for l in r["lines"]], ["Paid", "Short paid", "Rejected", "Unmatched", "Unmatched"])
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-C")["rejection_reason"], "card expired")

    def test_a_short_paid_claim_is_billed_back_through_the_door(self):
        self.booked()
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="REM-1", payer="GEN-INS",
                      lines=[{"name": "l1", "claim_ref": "GEN-INS-PHD-26-0001", "paid": "200"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "REM-1"), "remit")
        code, out = self.call("/icp/press/billback", press("PP ICP Claim", "GEN-INS-PHD-26-0001"), "billback")
        self.assertEqual(out["message"]["body"], "28.80 is owed by the customer again, on their own sale.")
        self.assertEqual(self.shop.billed, [{"sale": "PHD-26-0001", "claim_ref": "GEN-INS-PHD-26-0001",
                                             "amount": "28.80", "reason": "claim not paid"}])
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0001")["status"], "Billed to patient")

    def test_without_the_payer_door_nothing_is_billed_and_the_claim_is_unchanged(self):
        self.booked()
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="REM-1", payer="GEN-INS", lines=[
            {"name": "l1", "claim_ref": "GEN-INS-PHD-26-0001", "paid": "0", "rejected": 1, "reason": "x"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "REM-1"), "remit")
        self.shop.door = False
        code, out = self.call("/icp/press/billback", press("PP ICP Claim", "GEN-INS-PHD-26-0001"), "billback")
        self.assertEqual(out["message"]["level"], "warning")
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0001")["status"], "Rejected")

    def test_a_ready_claim_cannot_be_billed_back(self):
        self.booked()
        self.build()
        out = self.call("/icp/press/billback", press("PP ICP Claim", "GEN-INS-PHD-26-0001"), "billback")[1]
        self.assertEqual(out["message"]["body"], "A claim that is Ready cannot become Billed to patient.")
        self.assertEqual(self.shop.billed, [])


if __name__ == "__main__":
    unittest.main()
