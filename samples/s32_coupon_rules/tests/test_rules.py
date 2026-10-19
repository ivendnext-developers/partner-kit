"""S32's rules (``coupons.on_check``, ``coupons.rules_of``, ``coupons.check_context``): each rule bites, a coupon with no
rule or a switched-off rule is never refused, the count is asked only when a first-purchase rule needs it, and every
sentence is plain text the till accepts.

    python3 -m unittest discover -s samples/s32_coupon_rules/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import coupons  # noqa: E402

RECORDS = [{"name": "WELCOME10", "coupon": "WELCOME10", "enabled": 1, "first_purchase_only": 1, "customer_group": None},
           {"name": "STAFF15", "coupon": "STAFF15", "enabled": 1, "first_purchase_only": 0, "customer_group": "Staff"},
           {"name": "VIPNEW", "coupon": "VIPNEW", "enabled": 1, "first_purchase_only": 1, "customer_group": "VIP"},
           {"name": "OLD5", "coupon": "OLD5", "enabled": 0, "first_purchase_only": 1, "customer_group": "Staff"},
           {"name": "PLAIN", "coupon": "PLAIN", "enabled": 1, "first_purchase_only": 0, "customer_group": ""}]


def line(n=1, code="BREAD", qty=1, rate=1250):
    return {"line_no": n, "item_code": code, "item_group": "Bakery", "qty_milli": round(qty * 1000), "uom": "Nos",
            "rate_minor": rate, "amount_minor": round(rate * qty), "discount_minor": 0, "line_attributes": []}


def context(codes=(), customer="CUST-1", group="Retail", stage="sale", lines=None):
    lines = lines if lines is not None else [line()]
    grand = sum(x["amount_minor"] for x in lines)
    return {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "s-1", "store": "Main - S",
            "pos_profile": "Mall", "company": "Shop", "currency": "AED", "lang": "en", "operator": "c@shop.example",
            "customer": customer, "customer_group": group, "price_list": "Standard Selling", "coupon_codes": sorted(codes),
            "sale_attributes": [], "lines": lines,
            "totals": {"net_minor": grand, "tax_minor": 0, "discount_minor": 0, "grand_minor": grand},
            "offered_tenders": ["Cash", "Credit Card"]}


class Counter:
    """A stand-in for the shop's count of a customer's sales: answers from a dict, counts its calls."""

    def __init__(self, sales=None):
        self.sales, self.calls = sales or {}, []

    def __call__(self, customer):
        self.calls.append(customer)
        return self.sales.get(customer, 0)


RULES = coupons.rules_of(RECORDS)


class Rules(unittest.TestCase):
    def test_a_first_purchase_coupon_is_refused_for_a_customer_who_has_bought(self):
        out = coupons.on_check(context(["WELCOME10"]), RULES, Counter({"CUST-1": 3}))
        self.assertEqual(out, {"verdict": "refuse", "reason": "Coupon WELCOME10 is for a first purchase only; this "
                                                              "customer has bought before. Remove it, or add the new customer."})

    def test_a_first_purchase_coupon_is_allowed_for_a_new_customer(self):
        n = Counter({"CUST-9": 1})
        self.assertEqual(coupons.on_check(context(["WELCOME10"]), RULES, n), {"verdict": "allow"})
        self.assertEqual(n.calls, ["CUST-1"])

    def test_a_first_purchase_coupon_with_no_customer_is_refused_without_a_count(self):
        n = Counter()
        for none in ("", None):      # the contract sends text; a blank customer is no customer
            out = coupons.on_check(context(["WELCOME10"], customer=none), RULES, n)
            self.assertEqual(out["reason"], "Coupon WELCOME10 is for a first purchase only. Add the customer to the sale first.")
        self.assertEqual(n.calls, [])

    def test_a_group_coupon_is_refused_outside_its_group(self):
        out = coupons.on_check(context(["STAFF15"], group="Retail"), RULES, Counter())
        self.assertEqual(out, {"verdict": "refuse", "reason": "Coupon STAFF15 is only for customers in Staff. Remove it, "
                                                              "or add a customer in that group."})

    def test_a_group_coupon_is_allowed_in_its_group(self):
        self.assertEqual(coupons.on_check(context(["STAFF15"], group="Staff"), RULES, Counter()), {"verdict": "allow"})

    def test_a_group_matches_exactly_so_a_group_under_it_is_refused(self):
        self.assertEqual(coupons.on_check(context(["STAFF15"], group="Staff - Store 2"), RULES, Counter())["verdict"],
                         "refuse")

    def test_no_customer_group_is_outside_any_group(self):
        self.assertEqual(coupons.on_check(context(["STAFF15"], group=None), RULES, Counter())["verdict"], "refuse")

    def test_the_group_rule_is_judged_before_any_count(self):
        n = Counter()
        out = coupons.on_check(context(["VIPNEW"], group="Retail"), RULES, n)
        self.assertIn("only for customers in VIP", out["reason"])
        self.assertEqual(n.calls, [])

    def test_both_rules_on_one_coupon_both_hold(self):
        self.assertEqual(coupons.on_check(context(["VIPNEW"], group="VIP"), RULES, Counter()), {"verdict": "allow"})
        self.assertEqual(coupons.on_check(context(["VIPNEW"], group="VIP"), RULES, Counter({"CUST-1": 1}))["verdict"],
                         "refuse")

    def test_a_coupon_with_no_rule_or_a_switched_off_rule_is_never_refused(self):
        n = Counter({"CUST-1": 5})
        for code in ("NOTRULED", "OLD5", "PLAIN"):
            self.assertEqual(coupons.on_check(context([code], customer=None, group=None), RULES, n), {"verdict": "allow"},
                             code)
        self.assertEqual(n.calls, [])

    def test_a_sale_with_no_coupon_is_allowed_and_counts_nothing(self):
        n = Counter({"CUST-1": 5})
        self.assertEqual(coupons.on_check(context([]), RULES, n), {"verdict": "allow"})
        self.assertEqual(n.calls, [])

    def test_a_ruled_coupon_beside_an_unruled_one_is_still_judged(self):
        self.assertEqual(coupons.on_check(context(["NOTRULED", "WELCOME10"]), RULES, Counter({"CUST-1": 1}))["verdict"],
                         "refuse")

    def test_two_first_purchase_coupons_count_once(self):
        rules = coupons.rules_of(RECORDS + [{"coupon": "HELLO", "enabled": 1, "first_purchase_only": 1}])
        n = Counter()
        self.assertEqual(coupons.on_check(context(["HELLO", "WELCOME10"]), rules, n), {"verdict": "allow"})
        self.assertEqual(n.calls, ["CUST-1"])

    def test_a_return_that_sells_is_judged_too(self):
        ctx = context(["WELCOME10"], stage="return", lines=[line(1, qty=-1), line(2, "CAKE")])
        self.assertEqual(coupons.on_check(ctx, RULES, Counter({"CUST-1": 1}))["verdict"], "refuse")

    def test_every_sentence_is_plain_and_at_most_140(self):
        long = "W<b>" * 60
        rules = coupons.rules_of([{"coupon": long, "enabled": 1, "first_purchase_only": 1, "customer_group": long}])
        outs = [coupons.on_check(context([long], group="Retail"), rules, Counter()),
                coupons.on_check(context([long], group=long), rules, Counter({"CUST-1": 1})),
                coupons.on_check(context([long], group=long, customer=None), rules, Counter())]
        for out in outs:
            self.assertEqual(out["verdict"], "refuse")
            self.assertTrue(1 <= len(out["reason"]) <= 140, out["reason"])
            self.assertFalse(set("<>") & set(out["reason"]))
        for out in outs[1:]:      # the first-purchase sentences keep their instruction whole
            self.assertTrue(out["reason"].endswith(("Remove it, or add the new customer.", "Add the customer to the sale first.")), out)


class RulesOf(unittest.TestCase):
    def test_only_switched_on_records_that_name_a_coupon(self):
        self.assertEqual(sorted(RULES), ["PLAIN", "STAFF15", "VIPNEW", "WELCOME10"])
        self.assertEqual(RULES["WELCOME10"], {"first": True, "group": ""})
        self.assertEqual(RULES["STAFF15"], {"first": False, "group": "Staff"})

    def test_a_record_without_a_coupon_or_with_a_bad_group_is_harmless(self):
        out = coupons.rules_of([{"enabled": 1, "first_purchase_only": 1}, {"coupon": "X", "enabled": 1, "customer_group": 7}])
        self.assertEqual(out, {"X": {"first": False, "group": ""}})

    def test_anything_but_a_list_of_records_is_refused(self):
        for bad in (None, {"data": []}, ["x"], "[]"):
            with self.assertRaises(ValueError):
                coupons.rules_of(bad)


class Context(unittest.TestCase):
    def test_a_check_is_read(self):
        ctx = context(["WELCOME10"])
        self.assertIs(coupons.check_context({"point": "check/1", "context": ctx}), ctx)

    def test_a_bad_shape_is_refused_before_any_decision(self):
        for bad in ({"point": "capture/1", "context": context()}, {"point": "check/1", "context": {}},
                    {"point": "check/1", "context": dict(context(), coupon_codes="WELCOME10")},
                    {"point": "check/1", "context": dict(context(), coupon_codes=[1])},
                    {"point": "check/1", "context": dict(context(), customer=5)},
                    {"point": "check/1", "context": dict(context(), stage="layaway")}, []):
            with self.assertRaises(ValueError):
                coupons.check_context(bad)


class Verify(unittest.TestCase):
    def test_the_signature_and_the_time_are_checked(self):
        import base64
        import hashlib
        import hmac
        raw, ts = b'{"a":1}', "1000"
        sig = base64.b64encode(hmac.new(b"s", b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(coupons.verify(ts, sig, raw, "s", now=1000), "")
        self.assertTrue(coupons.verify(ts, sig, raw, "t", now=1000))
        self.assertTrue(coupons.verify(ts, sig, raw, "s", now=1000 + 301))
        self.assertTrue(coupons.verify(None, sig, raw, "s", now=1000))


if __name__ == "__main__":
    unittest.main()
