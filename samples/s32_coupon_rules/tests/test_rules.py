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
from decimal import Decimal  # noqa: E402

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


CAPPED = coupons.rules_of([{"coupon": "C100", "enabled": 1, "spend_per_use": 1000},
                           {"coupon": "C100B", "enabled": 1, "spend_per_use": 1000},
                           {"coupon": "C100C", "enabled": 1, "spend_per_use": 1000},
                           {"coupon": "MIN50", "enabled": 1, "spend_per_use": "50.005"},
                           {"coupon": "FIRSTCAP", "enabled": 1, "first_purchase_only": 1, "spend_per_use": 1000},
                           {"coupon": "GRPCAP", "enabled": 1, "customer_group": "Staff", "spend_per_use": 1000}])


def total(minor, exp=2):
    ctx = context()
    ctx["totals"] = dict(ctx["totals"], grand_minor=minor)
    ctx["currency_exponent"] = exp
    return ctx


def capped(codes, minor, exp=2, stage="sale", group="Retail"):
    ctx = total(minor, exp)
    ctx.update(coupon_codes=sorted(codes), stage=stage, customer_group=group)
    return ctx


class Cap(unittest.TestCase):
    """One coupon for each so much spent: the coupons on a sale may take at most floor(total / slice) uses."""

    def test_one_coupon_needs_its_sale(self):
        out = coupons.on_check(capped(["C100"], 99999), CAPPED, Counter())
        self.assertEqual(out, {"verdict": "refuse", "reason": "Coupon C100 needs a sale of AED 1,000.00; this sale is "
                                                              "AED 999.99. Remove a coupon, or add to the sale."})

    def test_exactly_the_sale_needed_is_allowed(self):
        self.assertEqual(coupons.on_check(capped(["C100"], 100000), CAPPED, Counter()), {"verdict": "allow"})

    def test_two_coupons_need_twice_the_sale(self):
        out = coupons.on_check(capped(["C100", "C100B"], 150000), CAPPED, Counter())
        self.assertEqual(out["reason"], "Coupons C100, C100B need a sale of AED 2,000.00; this sale is AED 1,500.00. "
                                        "Remove a coupon, or add to the sale.")
        self.assertEqual(coupons.on_check(capped(["C100", "C100B"], 200000), CAPPED, Counter()), {"verdict": "allow"})

    def test_floor_of_the_total_over_the_slice(self):
        for n, minor, verdict in ((3, 299999, "refuse"), (3, 300000, "allow"), (2, 299999, "allow")):
            codes = ["C100", "C100B", "C100C"][:n]
            self.assertEqual(coupons.on_check(capped(codes, minor), CAPPED, Counter())["verdict"], verdict, (n, minor))

    def test_an_uncapped_coupon_beside_takes_nothing(self):
        self.assertEqual(coupons.on_check(capped(["C100", "PLAIN", "NOTRULED"], 100000), dict(CAPPED, **RULES), Counter()),
                         {"verdict": "allow"})

    def test_the_amount_rounds_half_up_in_the_sales_currency(self):
        self.assertEqual(coupons.on_check(capped(["MIN50"], 5000), CAPPED, Counter())["verdict"], "refuse")
        self.assertEqual(coupons.on_check(capped(["MIN50"], 5001), CAPPED, Counter()), {"verdict": "allow"})
        self.assertEqual(coupons.on_check(capped(["MIN50"], 50, exp=0), CAPPED, Counter()), {"verdict": "allow"})  # no minor unit
        self.assertEqual(coupons.on_check(capped(["MIN50"], 49, exp=0), CAPPED, Counter())["reason"],
                         "Coupon MIN50 needs a sale of AED 50; this sale is AED 49. Remove a coupon, or add to the sale.")
        self.assertEqual(coupons.on_check(capped(["MIN50"], 49500, exp=3), CAPPED, Counter())["reason"],
                         "Coupon MIN50 needs a sale of AED 50.005; this sale is AED 49.500. Remove a coupon, or add to the sale.")

    def test_a_return_is_never_capped(self):
        self.assertEqual(coupons.on_check(capped(["C100"], 100, stage="return"), CAPPED, Counter()), {"verdict": "allow"})

    def test_the_cap_reads_nothing_and_comes_before_the_count(self):
        n = Counter({"CUST-1": 0})
        out = coupons.on_check(capped(["FIRSTCAP"], 500), CAPPED, n)
        self.assertIn("needs a sale of", out["reason"])
        self.assertEqual(n.calls, [])
        self.assertEqual(coupons.on_check(capped(["FIRSTCAP"], 100000), CAPPED, n), {"verdict": "allow"})
        self.assertEqual(n.calls, ["CUST-1"])

    def test_the_group_rule_comes_first(self):
        self.assertIn("only for customers in Staff", coupons.on_check(capped(["GRPCAP"], 500), CAPPED, Counter())["reason"])
        self.assertIn("needs a sale of", coupons.on_check(capped(["GRPCAP"], 500, group="Staff"), CAPPED, Counter())["reason"])

    def test_a_switched_off_capped_rule_caps_nothing(self):
        rules = coupons.rules_of([{"coupon": "OFF", "enabled": 0, "spend_per_use": 1000}])
        self.assertEqual(coupons.on_check(capped(["OFF"], 1), rules, Counter()), {"verdict": "allow"})

    def test_long_names_keep_the_amounts_and_the_instruction(self):
        names = ["N" * 60 + str(i) for i in range(5)]
        rules = coupons.rules_of([{"coupon": c, "enabled": 1, "spend_per_use": 999999999} for c in names])
        for codes in (names[:1], names):
            out = coupons.on_check(capped(codes, 1), rules, Counter())
            self.assertTrue(len(out["reason"]) <= 140, out["reason"])
            self.assertTrue(out["reason"].endswith("this sale is AED 0.01. Remove a coupon, or add to the sale."), out)
            self.assertFalse(set("<>") & set(out["reason"]))


class RulesOf(unittest.TestCase):
    def test_only_switched_on_records_that_name_a_coupon(self):
        self.assertEqual(sorted(RULES), ["PLAIN", "STAFF15", "VIPNEW", "WELCOME10"])
        self.assertEqual(RULES["WELCOME10"], {"first": True, "group": "", "spend": 0})
        self.assertEqual(RULES["STAFF15"], {"first": False, "group": "Staff", "spend": 0})

    def test_a_record_without_a_coupon_or_with_a_bad_group_is_harmless(self):
        out = coupons.rules_of([{"enabled": 1, "first_purchase_only": 1}, {"coupon": "X", "enabled": 1, "customer_group": 7}])
        self.assertEqual(out, {"X": {"first": False, "group": "", "spend": 0}})

    def test_a_sale_needed_is_a_positive_amount_or_nothing(self):
        for value, want in ((1000, 1000), (1000.5, Decimal("1000.5")), ("250", 250), (0, 0), (None, 0), (-5, 0),
                            (True, 0), ("abc", 0), ("NaN", 0), ("Infinity", 0), ([1], 0)):
            out = coupons.rules_of([{"coupon": "C", "enabled": 1, "spend_per_use": value}])
            self.assertEqual(out["C"]["spend"], want, value)
        self.assertEqual(coupons.rules_of([{"coupon": "C", "enabled": 1}])["C"]["spend"], 0)   # a record from 1.0.1

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
                    {"point": "check/1", "context": dict(context(), stage="layaway")},
                    {"point": "check/1", "context": dict(context(), currency_exponent=True)},
                    {"point": "check/1", "context": dict(context(), currency_exponent=5)},
                    {"point": "check/1", "context": dict(context(), totals={"grand_minor": "1250"})},
                    {"point": "check/1", "context": dict(context(), totals=None)}, []):
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
