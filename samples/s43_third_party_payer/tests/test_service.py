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
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(SAMPLE)), "contracts"))
import app  # noqa: E402
import extension_contract_check as contract  # noqa: E402
from fake_shop import FakeShop  # noqa: E402

SECRETS = {k: f"s-{k}" for k in ("payer", "claims", "file", "remit", "ready", "settle", "billback")}
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


def door_line(l):
    if "amount" not in l:
        return dict(l)
    out = {k: v for k, v in l.items() if k not in ("amount", "discount")}
    amount, disc = round(float(l["amount"]) * 100), round(float(l.get("discount") or 0) * 100)
    out = dict({"item_group": "", "gtin": None, "uom": "Nos", "conversion_factor": 1}, **out)
    out.update(amount_minor=amount, discount_minor=disc, rate_minor=round(amount / float(out.get("qty") or 1)))
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.shop = FakeShop().generic()
        self.svc = app.Service(conf(), api=self.shop, now=lambda: NOW)

    def call(self, path, body, key, **kw):
        headers, raw = signed(body, key, **kw)
        return self.svc.handle("POST", path, headers, raw)

    def payer(self, body):
        """A signed call as the door sends it: ``{"point": "payer/1", "context": {v, point, call, …}}``."""
        return self.call("/icp/payer", {"point": "payer/1", "context": dict({"v": 1, "point": "payer"}, **body)},
                         "payer")

    def coverage(self, **kw):
        """The door's coverage ask; a test line's ``amount`` and ``discount`` (in KES) are sent in minor units."""
        lines = [door_line(l) for l in kw.pop("lines", LINES)]
        body = {"call": "coverage", "sale_ref": "PHD-26-0001", "customer": "C1", "member": "m1", "date": "2026-10-23",
                "currency": "KES", "currency_exponent": 2, "store": "Pharmacy Dispensary", "pos_profile": "PHD",
                "operator": "cashier@example.com", "price_list": "Generic Insurer Prices", "tax_included": True,
                "prescription": None, "lines": lines, "total_minor": sum(l["amount_minor"] for l in lines),
                "rounding_minor": 0}
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
                                                 "promotions_apply": True})
        self.assertNotIn("GEN-000123", json.dumps(out))

    def test_a_barred_customer_has_no_cover(self):
        code, out = self.payer({"call": "covers", "customer": "C2", "date": "2026-10-23"})
        self.assertEqual((code, out["covers"], out["refused"]["code"]), (200, [], "barred"))

    def test_coverage_answers_the_contract(self):
        code, out = self.coverage()
        self.assertEqual((code, out["answer"], out["claim_ref"]), (200, "cover", "GEN-INS-PHD-26-0001"))
        self.assertEqual(out["totals"], {"payer_share_minor": 22880, "patient_share_minor": 6120, "total_minor": 29000})
        self.assertEqual(set(out), {"answer", "payer", "plan", "member", "claim_ref", "no_partial_refund", "lines",
                                    "totals"})
        for l in out["lines"]:
            self.assertEqual(set(l), {"line_id", "covered", "sellable", "payer_share_minor", "patient_share_minor",
                                      "covered_qty", "qty_limit", "reason", "message"})

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

    def test_a_sale_in_another_currency_than_the_plans_list_has_no_cover(self):
        out = self.coverage(currency="USD")[1]
        self.assertEqual((out["answer"], out["code"]), ("no_cover", "plan_currency"))

    def test_a_line_in_a_pack_unit_takes_the_stock_units_price_times_the_pack(self):
        # listed per tablet (the stock unit), sold by the box of 10: the engine prices it 10 x; it is on the list
        self.shop.tables["Item Price"] = [{"item_code": "PHD-AMOX-500", "price_list": "Generic Insurer Prices",
                                           "uom": "Nos", "price_list_rate": 12}]
        out = self.coverage(lines=[dict(LINES[0], uom="Box", conversion_factor=10, qty=1, amount=120)])[1]
        self.assertEqual((out["answer"], out["lines"][0]["reason"]), ("cover", None))
        self.shop.tables["Item Price"][0]["price_list_rate"] = 0
        self.assertEqual(self.coverage(lines=[dict(LINES[0], uom="Box", conversion_factor=10, qty=1,
                                                   amount=120)])[1]["lines"][0]["reason"], "zero_on_list")

    def test_a_line_not_at_the_sales_precision_or_a_repeated_line_id_is_refused(self):
        self.assertEqual(self.coverage(lines=[dict(door_line(LINES[0]), amount_minor=3333.0)], total_minor=3333)[0], 400)
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
        out = self.coverage()[1]       # the door sends item_group "": OTC carries 2 a unit of extra-item pay
        self.assertEqual(out["lines"][1]["patient_share_minor"], 1320)     # 4.00 + 20% of 46.00; uncovered: 5000

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


SCHEMA = contract._schema("payer")


def contract_errors(kind, answer):
    """What the payer door's own contract (the kit's copy, equal to the POS app's) finds wrong with an answer."""
    return contract._errors(SCHEMA["$defs"][kind], answer, SCHEMA)


class Door(Base):
    """Every answer this service gives the door is one the door's contract takes, and its arithmetic the door's."""

    def test_every_answer_is_one_the_doors_contract_takes(self):
        answers = [self.payer({"call": "covers", "customer": "C1", "date": "2026-10-23", "store": "S",
                               "pos_profile": "PHD", "operator": "o"})[1],
                   self.payer({"call": "covers", "customer": "C2", "date": "2026-10-23", "store": "S",
                               "pos_profile": "PHD", "operator": "o"})[1]]
        for a in answers:
            self.assertEqual(contract_errors("covers_answer", a), [], a)
        for kw in ({}, {"lines": LINES + [{"line_id": "r3", "item_code": "PHD-VITC", "qty": 1, "amount": 30}]},
                   {"currency": "USD"}, {"member": "m2"}):
            out = self.coverage(**kw)[1]
            self.assertEqual(contract_errors("coverage_answer", out), [], (kw, out))
        self.assertEqual([self.coverage(**kw)[1]["answer"] for kw in ({}, {"lines": LINES + [
            {"line_id": "r3", "item_code": "PHD-VITC", "qty": 1, "amount": 30}]}, {"member": "m2"})],
                         ["cover", "refuse", "no_cover"])

    def test_a_cover_answers_each_line_once_its_shares_adding_up_to_the_line(self):
        ask = self.coverage()[1]
        sent = {l["line_id"]: door_line(l) for l in LINES}
        for l in ask["lines"]:
            self.assertEqual(l["payer_share_minor"] + l["patient_share_minor"], sent[l["line_id"]]["amount_minor"])
        self.assertEqual(sorted(l["line_id"] for l in ask["lines"]), sorted(sent))

    def test_a_pack_lines_covered_quantity_is_in_the_lines_own_unit(self):
        self.shop.tables["Item Price"] = [{"item_code": "PHD-AMOX-500", "price_list": "Generic Insurer Prices",
                                           "uom": "Nos", "price_list_rate": 12}]
        out = self.coverage(lines=[dict(LINES[0], uom="Box", conversion_factor=10, qty=1, amount=120)])[1]
        self.assertEqual((out["answer"], out["lines"][0]["covered_qty"]), ("cover", 1.0))   # 10 tablets: 1 box

    def test_the_payers_share_never_passes_the_rounded_total(self):
        plan = self.shop.find("PP ICP Plan", "Generic Silver")
        plan.update(copay_percent=0, invoice_upper_limit=0)
        self.shop.find("PP ICP Formulary", plan["formulary"])["rows"] = [{"item_group": "Prescription Medicines",
                                                                         "covered": 1}]
        line = [dict(LINES[0], amount=240.03)]
        full = self.coverage(lines=line)[1]
        self.assertEqual(full["totals"]["patient_share_minor"], 0)
        down = self.coverage(lines=line, rounding_minor=-3)[1]                  # the till rounds 240.03 to 240.00
        self.assertEqual((down["totals"]["payer_share_minor"], down["totals"]["patient_share_minor"]), (24000, 3))

    def test_a_tax_excluded_sales_discount_is_read_with_its_tax(self):
        plan = self.shop.find("PP ICP Plan", "Generic Silver")
        plan.update(copay_percent=20, copay_order="Before the discount", invoice_upper_limit=0, max_patient_amount=0)
        # 2 x 100 before tax, 20 off, 16% tax: the line costs 208.80; the discount on the amount's basis is 23.20
        line = {"line_id": "r1", "item_code": "PHD-AMOX-500", "item_group": "", "gtin": None, "qty": 2, "uom": "Nos",
                "conversion_factor": 1, "rate_minor": 9000, "discount_minor": 2000, "amount_minor": 20880}
        inc = self.coverage(lines=[dict(line)], tax_included=True)[1]
        exc = self.coverage(lines=[dict(line)], tax_included=False)[1]
        self.assertEqual(inc["totals"]["patient_share_minor"], round(0.2 * (20880 + 2000)))
        self.assertEqual(exc["totals"]["patient_share_minor"], round(0.2 * (20880 + 2320)))

    def test_a_cover_that_would_pay_nothing_is_no_cover(self):
        out = self.coverage(lines=[{"line_id": "r1", "item_code": "PHD-PARA-500", "qty": 1, "amount": 2}])[1]
        self.assertEqual((out["answer"], out["code"]), ("no_cover", "pays_nothing"))
        self.assertEqual(contract_errors("coverage_answer", out), [])

    def test_a_payer_whose_customer_is_the_sales_own_is_never_offered(self):
        self.shop.find("PP ICP Payer", "GEN-INS")["customer"] = "C1"
        self.assertEqual(self.payer({"call": "covers", "customer": "C1", "date": "2026-10-23"})[1]["covers"], [])

    def test_every_exponent_the_door_sends_gets_an_answer_it_takes(self):
        for exp in range(5):                       # JPY 0 · a 1-digit currency · USD 2 · KWD 3 · a 4-digit unit
            f = 10 ** exp
            lines = [{"line_id": "r1", "item_code": "PHD-AMOX-500", "item_group": "", "gtin": None, "qty": 3,
                      "uom": "Nos", "conversion_factor": 1, "rate_minor": 120 * f, "discount_minor": 0,
                      "amount_minor": 360 * f + (1 if exp else 0)},
                     {"line_id": "r2", "item_code": "PHD-PARA-500", "item_group": "", "gtin": None, "qty": 2,
                      "uom": "Nos", "conversion_factor": 1, "rate_minor": 25 * f, "discount_minor": 0,
                      "amount_minor": 50 * f}]
            out = self.coverage(lines=lines, currency_exponent=exp, rounding_minor=-1 if exp else 0)[1]
            self.assertEqual(contract_errors("coverage_answer", out), [], exp)
            self.assertEqual(out["answer"], "cover", exp)
            for l in out["lines"]:
                sent = next(x for x in lines if x["line_id"] == l["line_id"])
                self.assertEqual(l["payer_share_minor"] + l["patient_share_minor"], sent["amount_minor"], exp)
            self.assertEqual(out["totals"]["total_minor"], sum(x["amount_minor"] for x in lines), exp)
            self.assertGreaterEqual(out["totals"]["patient_share_minor"] + (-1 if exp else 0), 0, exp)

    def test_a_disabled_payer_customer_leaves_that_cover_out_not_the_answer(self):
        self.shop.find("Customer", "Generic Insurer")["disabled"] = 1
        code, out = self.payer({"call": "covers", "customer": "C1", "date": "2026-10-23"})
        self.assertEqual((code, out["covers"], out["refused"]), (200, [], None))
        self.assertEqual(contract_errors("covers_answer", out), [])

    def test_a_title_with_markup_is_sent_as_text_the_door_takes(self):
        self.shop.find("PP ICP Plan", "Generic Silver")["title"] = "Silver <Rx>\u202e plan"
        covers = self.payer({"call": "covers", "customer": "C1", "date": "2026-10-23"})[1]
        self.assertEqual(covers["covers"][0]["plan_title"], "Silver Rx plan")
        out = self.coverage(lines=LINES + [{"line_id": "r3", "item_code": "PHD-VITC", "qty": 1, "amount": 30}])[1]
        for l in out["lines"]:
            self.assertFalse(set(l.get("message") or "") & set("<>\u202e"), l)

    def test_a_sales_discount_on_prices_without_tax_is_read_with_at_most_its_tax(self):
        # one line at 100.00 before tax, a 50.00 discount on the whole sale, 10% tax: the line costs 55.00, and the
        # door sends discount_minor 5000 on the price's basis. The ratio is then 55/100 < 1: the discount is read as
        # sent (the bound), never with less than itself (a co-pay of 20% before the discount: 21.00, never 16.50)
        plan = self.shop.find("PP ICP Plan", "Generic Silver")
        plan.update(copay_percent=20, copay_order="Before the discount", invoice_upper_limit=0, max_patient_amount=0)
        line = {"line_id": "r1", "item_code": "PHD-AMOX-500", "item_group": "", "gtin": None, "qty": 1, "uom": "Nos",
                "conversion_factor": 1, "rate_minor": 10000, "discount_minor": 5000, "amount_minor": 5500}
        out = self.coverage(lines=[line], tax_included=False)[1]
        self.assertEqual(out["totals"]["patient_share_minor"], 2100)

    def test_a_desk_invoice_not_priced_on_the_plans_list_is_no_cover_in_words(self):
        # a Desk invoice keeps its own list (payer.md §7); split on the store's price it would claim the wrong tariff
        out = self.coverage(price_list="Standard Selling")[1]
        self.assertEqual((out["answer"], out["code"]), ("no_cover", "plan_list"))
        self.assertIn("put the invoice on that price list", out["message"])
        self.assertEqual(contract_errors("coverage_answer", out), [])

    def test_the_old_wire_is_refused(self):
        old = {"contract": "payer/1", "call": "covers", "customer": "C1"}
        self.assertEqual(self.call("/icp/payer", old, "payer")[0], 400)
        self.assertEqual(self.coverage(lines=[dict(LINES[0])], total_minor=1)[0], 400)   # lines not adding up
        ctx = {"v": 1, "point": "payer", "call": "covers", "customer": "C1", "date": "2026-10-23"}
        self.assertEqual(self.call("/icp/payer", {"point": "check/1", "context": ctx}, "payer")[0], 400)
        self.assertEqual(self.call("/icp/payer", {"point": "payer/1", "context": ctx}, "payer")[0], 200)


def door_lines(answer, asked=LINES):
    """The lines the door stores from a cover answer: each share in the sale's currency (the answer is in minor
    units)."""
    code = {l["line_id"]: l["item_code"] for l in asked}
    return [{"name": l["line_id"], "item_code": code[l["line_id"]], "qty": float(l["covered_qty"]), "stock_qty":
             float(l["covered_qty"]), "uom": "Nos", "barcode": "0612345678901", "warehouse": "Pharmacy Dispensary",
             "payer_share": f"{l['payer_share_minor'] / 100:.2f}", "patient_share": f"{l['patient_share_minor'] / 100:.2f}",
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

    def test_the_clerk_marks_a_claim_ready_only_once_complete_and_a_corrected_one_goes_again(self):
        self.shop.book("S-1", door_lines(self.coverage(sale_ref="S-1")[1]), payer_prescription=None)
        self.build()
        c = self.shop.find("PP ICP Claim", "GEN-INS-S-1")
        self.assertEqual(c["status"], "Incomplete")
        out = self.call("/icp/press/ready", press("PP ICP Claim", "GEN-INS-S-1"), "ready")[1]
        self.assertEqual(out["message"]["level"], "warning")                  # the prescription is still missing
        c["prescription"] = "RX-77"
        self.call("/icp/press/ready", press("PP ICP Claim", "GEN-INS-S-1"), "ready")
        self.assertEqual(c["status"], "Ready")
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="R", payer="GEN-INS",
                      lines=[{"name": "l", "claim_ref": "GEN-INS-S-1", "paid": "0", "rejected": 1, "reason": "x"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "R"), "remit")
        self.call("/icp/press/ready", press("PP ICP Claim", "GEN-INS-S-1"), "ready")
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.assertEqual((c["status"], c["resubmissions"]), ("Resubmitted", 1))

    def test_only_a_short_paid_claim_is_settled_as_it_stands(self):
        self.booked("S-1")
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        out = self.call("/icp/press/settle", press("PP ICP Claim", "GEN-INS-S-1"), "settle")[1]
        self.assertEqual(out["message"]["level"], "warning")                  # sent, not short-paid: never closed
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-S-1")["status"], "Submitted")
        self.shop.add("PP ICP Remittance", name="R", payer="GEN-INS",
                      lines=[{"name": "l", "claim_ref": "GEN-INS-S-1", "paid": "200"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "R"), "remit")
        self.call("/icp/press/settle", press("PP ICP Claim", "GEN-INS-S-1"), "settle")
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-S-1")["status"], "Paid")

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

    def test_a_sale_whose_booking_journal_was_cancelled_is_no_claim(self):
        # payer.md §4b: its day's closing cancelled on a shop that posts each sale at once took its journal with it
        out = self.coverage(sale_ref="PHD-26-0009")[1]
        self.shop.book("PHD-26-0009", door_lines(out), payer_journal=None)
        self.build()
        self.assertIsNone(self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0009"))

    def test_a_returned_line_counts_back_in_its_own_unit(self):
        # a box of 10 sold and returned: the claim line and its return are both counted in boxes
        self.shop.book("PHD-26-0010", [{"name": "b1", "item_code": "PHD-AMOX-500", "qty": 1, "stock_qty": 10,
                                        "uom": "Box", "payer_share": "96.00", "patient_share": "24.00",
                                        "payer_covered_qty": 1}])
        self.build()
        self.shop.book("PHD-26-0010-RET", [{"name": "x1", "item_code": "PHD-AMOX-500", "qty": -1, "stock_qty": -10,
                                            "uom": "Box", "pos_invoice_item": "b1", "payer_back": "-96.00"}],
                       is_return=1, return_against="PHD-26-0010", payer_claim_ref="GEN-INS-PHD-26-0010")
        self.build()
        line = self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0010")["lines"][0]
        self.assertEqual((float(line["qty"]), float(line["returned_qty"])), (1.0, 1.0))

    def test_a_claim_whose_sale_was_cancelled_after_it_was_built_never_goes_in_a_file(self):
        self.booked("PHD-26-0011")
        self.booked("PHD-26-0012")
        self.build()
        self.shop.find("POS Invoice", "PHD-26-0012").update(docstatus=2, custom_mpos_payer_journal=None)
        code, out = self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.assertIn("1 taken out: their sale was cancelled.", out["message"]["body"])
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0012")["status"], "Returned")
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0011")["status"], "Submitted")

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

    def test_a_bill_back_the_door_refuses_says_why_and_leaves_the_claim(self):
        self.booked()
        self.build()
        self.call("/icp/press/file", press("PP ICP Payer", "GEN-INS"), "file")
        self.shop.add("PP ICP Remittance", name="REM-1", payer="GEN-INS", lines=[
            {"name": "l1", "claim_ref": "GEN-INS-PHD-26-0001", "paid": "0", "rejected": 1, "reason": "x"}])
        self.call("/icp/press/remit", press("PP ICP Remittance", "REM-1"), "remit")
        self.shop.refuse = "This sale is posted at the day's close. Bill it back after the close."
        code, out = self.call("/icp/press/billback", press("PP ICP Claim", "GEN-INS-PHD-26-0001"), "billback")
        self.assertEqual((out["message"]["level"], out["message"]["body"]),
                         ("warning", "Nothing was billed: This sale is posted at the day's close. Bill it back after "
                                     "the close."))
        self.assertEqual(self.shop.find("PP ICP Claim", "GEN-INS-PHD-26-0001")["status"], "Rejected")

    def test_the_doors_refusal_is_read_from_the_shops_answer(self):
        import urllib.error
        body = json.dumps({"_server_messages": json.dumps([json.dumps({"message": "Say why the claim is billed back."})])})
        err = urllib.error.HTTPError("https://shop.example/x", 417, "Expectation Failed", {}, io.BytesIO(body.encode()))
        self.assertEqual(app._refusal(err), "Say why the claim is billed back.")
        err = urllib.error.HTTPError("https://shop.example/x", 417, "Expectation Failed", {}, io.BytesIO(b"<html>"))
        self.assertEqual(app._refusal(err), "The payer door refused it.")

    def test_a_long_refusal_fits_the_doors_answer_and_a_broken_body_is_read_as_a_refusal(self):
        import urllib.error

        class Broken(io.BytesIO):
            def read(self, *a):
                raise OSError("timed out")
        long = json.dumps({"_server_messages": json.dumps([json.dumps({"message": "x" * 900})])}).encode()
        text = app._refusal(urllib.error.HTTPError("https://shop.example/x", 417, "E", {}, io.BytesIO(long)))
        self.assertLessEqual(len("Nothing was billed: " + text), 280)
        err = urllib.error.HTTPError("https://shop.example/x", 417, "E", {}, Broken())
        self.assertEqual(app._refusal(err), "The payer door refused it.")

    def test_the_shops_417_on_a_bill_back_comes_back_as_the_doors_words(self):
        import urllib.error
        import urllib.request
        body = json.dumps({"_server_messages": json.dumps([json.dumps({"message": "Bill back an amount above zero."})])})

        class Opener:
            def open(self, req, timeout=None):
                raise urllib.error.HTTPError(req.full_url, 417, "E", {}, io.BytesIO(body.encode()))
        keep = urllib.request.build_opener
        urllib.request.build_opener = lambda *a: Opener()
        try:
            got = app.ShopApi().bill_back("https://shop.example", "k:s", {"sale": "S"})
        finally:
            urllib.request.build_opener = keep
        self.assertEqual(got, {"refused": "Bill back an amount above zero."})

    def test_a_ready_claim_cannot_be_billed_back(self):
        self.booked()
        self.build()
        out = self.call("/icp/press/billback", press("PP ICP Claim", "GEN-INS-PHD-26-0001"), "billback")[1]
        self.assertEqual(out["message"]["body"], "A claim that is Ready cannot become Billed to patient.")
        self.assertEqual(self.shop.billed, [])


if __name__ == "__main__":
    unittest.main()


class ManyShops(unittest.TestCase):
    """The App library's hosted copy: one service, many shops (tools/app_template/service/shops.py), the prefix
    IVENDNEXT ICP. A COPY of samples/s51_refund_rules/tests/test_service.py ManyShops' shape (a defect there is a
    defect here)."""
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        import shops
        import tempfile
        self.store = shops.FileStore(os.path.join(tempfile.mkdtemp(), "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_icp:sub:payer": f"payer-{n}", "user:icp@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_icp:sub:payer": "payer-c"}})   # no user key
        self.shop = FakeShop().generic()
        for c in self.shop.rows("Customer"):
            if "pp_icp_insurance_barred" in c:
                c["ivendnext_icp_insurance_barred"] = c.pop("pp_icp_insurance_barred")
        for dt in [d for d in list(self.shop.tables) if d.startswith("PP ICP ")]:
            self.shop.tables["IVENDNEXT ICP " + dt[len("PP ICP "):]] = self.shop.tables.pop(dt)
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_icp", "ICP_PREFIX": "IVENDNEXT ICP"}, store=self.store,
                               api=self.shop, now=lambda: NOW)

    def covers(self, secret, site, customer="C2"):
        body = {"point": "payer/1", "context": {"v": 1, "point": "payer", "call": "covers", "customer": customer,
                                                "date": "2026-10-23"}}
        raw = json.dumps(body).encode()
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        headers = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if site:
            headers[app.shops.SITE_HEADER] = site
        return self.svc.handle("POST", "/icp/payer", headers, raw)

    def test_each_shop_is_read_with_its_own_key_and_the_librarys_prefix(self):
        # C2 is barred under the library's field name (ivendnext_icp_insurance_barred), on either shop's own secret
        self.assertEqual(self.covers("payer-a", self.A)[1]["refused"]["code"], "barred")
        self.assertEqual(self.covers("payer-b", self.B)[1]["refused"]["code"], "barred")
        self.assertEqual(self.covers("payer-a", self.A, customer="C1")[1]["covers"][0]["plan"], "Generic Silver")

    def test_another_shops_secret_an_unknown_site_and_no_site_are_refused(self):
        self.assertEqual(self.covers("payer-b", self.A)[0], 401)
        self.assertEqual(self.covers("payer-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.covers("payer-a", None)[0], 401)

    def test_a_shop_without_its_integration_key_is_a_503_the_door_reads_as_no_cover(self):
        self.assertEqual(self.covers("payer-c", "shop-c.ivendnext.com")[0], 503)
