"""S34's rules, on the pure core with the stand-in ERP: a held supplier is refused, an order over the buyer's budget asks
a Purchase Manager, a clear order is filled with the ERP's number; and the shape a call must have.

    python3 -m unittest discover -s samples/s34_po_check/tests -p 'test_*.py'
"""

import copy
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import erp  # noqa: E402
import po_check  # noqa: E402

FIELD = "pp_poc_erp_number"


def context(supplier="Globe Traders", minor=150000, currency="USD", user="buyer@shop.example", name="PUR-ORD-2026-00118",
            event="submit", company="Demo Retail"):
    return {"v": 1, "event": event, "doctype": "Purchase Order", "name": name, "company": company, "user": user,
            "lang": "en", "fields": {"name": name, "supplier": supplier,
                                     "grand_total": {"currency": currency, "currency_exponent": 2, "minor": minor},
                                     "items": [{"item_code": "SKU-1", "qty": 50000}]}}


def body(ctx):
    return {"point": "doccheck/1", "context": ctx}


class Rules(unittest.TestCase):
    def setUp(self):
        self.erp = erp.StandIn()

    def answer(self, **k):
        return po_check.on_check(po_check.check_context(body(context(**k))), self.erp, FIELD)

    def test_a_held_supplier_is_refused_with_the_erps_reason(self):
        self.assertEqual(self.answer(supplier="Acme Supplies"),
                         {"verdict": "refuse", "reason": "The ERP holds this supplier: invoice 4471 is unpaid."})

    def test_an_order_over_the_companys_budget_asks_a_purchase_manager(self):
        # the company has 10,000.00 a month and has ordered 2,500.00: 7,500.00 left
        a = self.answer(minor=800000)
        self.assertEqual((a["verdict"], a["role"]), ("approve", "Purchase Manager"))
        self.assertEqual(a["reason"], "Over the monthly budget: 7,500.00 USD left.")

    def test_an_order_just_inside_the_budget_is_filled(self):
        self.assertEqual(self.answer(minor=750000)["verdict"], "fill")

    def test_a_clear_order_is_filled_with_the_erps_number_once(self):
        first = self.answer()
        self.assertEqual(first, {"verdict": "fill", "fields": {FIELD: "ERP-PO-9912"}})
        self.assertEqual(self.answer(), first)                                      # the same order: the same number
        self.assertEqual(self.answer(name="PUR-ORD-2026-00119")["fields"][FIELD], "ERP-PO-9913")

    def test_the_hold_is_asked_before_the_budget(self):
        self.assertEqual(self.answer(supplier="Acme Supplies", minor=99999999)["verdict"], "refuse")

    def test_the_budget_is_the_companys_whoever_submits(self):
        # a purchase manager, or a colleague, submitting the same order meets the same approval
        for user in ("buyer@shop.example", "manager@shop.example", "colleague@shop.example"):
            self.assertEqual(self.answer(user=user, minor=800000)["verdict"], "approve", user)

    def test_a_company_not_named_has_the_default_budget(self):
        self.assertEqual(self.answer(company="Other Co", minor=1000001)["verdict"], "approve")
        self.assertEqual(self.answer(company="Other Co", minor=1000000, name="PUR-ORD-2026-00120")["verdict"], "fill")

    def test_a_currency_with_no_budget_is_not_held_by_budget(self):
        self.assertEqual(self.answer(currency="EUR", minor=99999999)["verdict"], "fill")

    def test_a_draft_save_is_allowed(self):
        self.assertEqual(self.answer(event="validate", supplier="Acme Supplies"), {"verdict": "allow"})

    def test_sentences_are_plain_text_and_short(self):
        self.erp.data["held_suppliers"]["Long Ltd"] = "<b>" + "x" * 300 + "</b>"
        reason = self.answer(supplier="Long Ltd")["reason"]
        self.assertLessEqual(len(reason), po_check.TEXT_MAX)
        self.assertNotIn("<", reason)


class Shape(unittest.TestCase):
    def refused(self, change):
        b = body(context())
        change(b)
        with self.assertRaises(ValueError):
            po_check.check_context(b)

    def test_a_call_this_app_cannot_read_is_refused(self):
        self.refused(lambda b: b.update(point="check/1"))
        self.refused(lambda b: b["context"].update(v=2))
        self.refused(lambda b: b["context"].update(doctype="Purchase Receipt"))
        self.refused(lambda b: b["context"]["fields"].pop("supplier"))
        self.refused(lambda b: b["context"]["fields"]["grand_total"].update(minor=1500.0))
        self.refused(lambda b: b["context"].update(fields=None))

    def test_a_good_call_is_read(self):
        self.assertEqual(po_check.check_context(body(context()))["name"], "PUR-ORD-2026-00118")

    def test_the_signature(self):
        raw, secret = b'{"a":1}', "s3cret"
        import base64, hashlib, hmac  # noqa: E401
        sig = base64.b64encode(hmac.new(secret.encode(), b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(po_check.verify("1000", sig, raw, secret, now=1000), "")
        self.assertTrue(po_check.verify("1000", sig, raw + b" ", secret, now=1000))
        self.assertTrue(po_check.verify("1000", sig, raw, "other", now=1000))
        self.assertTrue(po_check.verify("1000", sig, raw, secret, now=1000 + po_check.SKEW_S + 1))
        self.assertTrue(po_check.verify(None, sig, raw, secret, now=1000))


if __name__ == "__main__":
    unittest.main()
