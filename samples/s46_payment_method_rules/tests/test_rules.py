"""S46's rules (``payrules.on_check``, ``payrules.deciding``, ``payrules.rules_of``, ``payrules.tree_of``,
``payrules.check_context``): each kind of rule leaves out the right methods, the nearest rule up the tree decides, a sale
the rule leaves nothing to pay with is refused, a refund is never judged, and every sentence is plain text the till accepts.

    python3 -m unittest discover -s samples/s46_payment_method_rules/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import payrules  # noqa: E402

ONLY, BUT = payrules.ONLY, payrules.BUT

# the shop's list read: one row per method (a rule with no method row comes once with none, a left join)
RECORDS = [
    {"name": "All Customer Groups", "customer_group": "All Customer Groups", "kind": BUT, "words": None, "mode_of_payment": "On Account"},
    {"name": "Account customers", "customer_group": "Account customers", "kind": BUT, "words": None, "mode_of_payment": "Gift Certificate"},
    {"name": "Talabat", "customer_group": "Talabat", "kind": ONLY, "words": "Talabat customers pay with Talabat.",
     "mode_of_payment": "Talabat"},
    {"name": "USD customers", "customer_group": "USD customers", "kind": ONLY, "words": "", "mode_of_payment": "Cash USD"},
    {"name": "USD customers", "customer_group": "USD customers", "kind": ONLY, "words": "", "mode_of_payment": "Card USD"},
]
# All Customer Groups (1, 16) > Account customers (2, 7) > Gold accounts (3, 4) · Contractors (5, 6)
#                             > Retail (8, 9) · Talabat (10, 11) · USD customers (12, 13) · Staff (14, 15)
TREE_ROWS = [{"name": "All Customer Groups", "lft": 1, "rgt": 16}, {"name": "Account customers", "lft": 2, "rgt": 7},
             {"name": "Gold accounts", "lft": 3, "rgt": 4}, {"name": "Contractors", "lft": 5, "rgt": 6},
             {"name": "Retail", "lft": 8, "rgt": 9}, {"name": "Talabat", "lft": 10, "rgt": 11},
             {"name": "USD customers", "lft": 12, "rgt": 13}, {"name": "Staff", "lft": 14, "rgt": 15}]
OFFERED = ["Cash", "Credit Card", "On Account", "Gift Certificate", "Talabat", "Cash USD", "Card USD"]


def line(n=1, code="BREAD", qty=1, rate=1250):
    return {"line_no": n, "item_code": code, "item_group": "Bakery", "qty_milli": round(qty * 1000), "uom": "Nos",
            "rate_minor": rate, "amount_minor": round(rate * qty), "discount_minor": 0, "line_attributes": []}


def context(group="Retail", customer="CUST-1", offered=None, stage="sale", lines=None):
    lines = lines if lines is not None else [line()]
    grand = sum(x["amount_minor"] for x in lines)
    ctx = {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "s-1", "store": "Main - S",
           "pos_profile": "Mall", "company": "Shop", "currency": "AED", "lang": "en", "operator": "c@shop.example",
           "customer": customer, "customer_group": group, "price_list": "Standard Selling", "coupon_codes": [],
           "sale_attributes": [], "lines": lines,
           "totals": {"net_minor": grand, "tax_minor": 0, "discount_minor": 0, "grand_minor": grand},
           "offered_tenders": list(OFFERED if offered is None else offered), "pos_opening": "POS-OPE-1",
           "pos_terminal": "Mall Counter 2"}
    if stage == "return":
        ctx["return_of"] = {"invoice": "SINV-1", "channel": "pos", "paid_by": ["Cash"]}
    return ctx


RULES, TREE = payrules.rules_of(RECORDS), payrules.tree_of(TREE_ROWS)


def check(**kw):
    return payrules.on_check(context(**kw), RULES, TREE)


class Rules(unittest.TestCase):
    def test_only_these_leaves_out_every_other_offered_method(self):
        self.assertEqual(check(group="Talabat"), {
            "verdict": "allow", "exclude_tenders": ["Cash", "Credit Card", "On Account", "Gift Certificate", "Cash USD", "Card USD"],
            "reason": "Talabat customers pay with Talabat."})

    def test_every_method_but_these_leaves_out_the_listed_ones(self):
        self.assertEqual(check(group="Account customers"), {
            "verdict": "allow", "exclude_tenders": ["Gift Certificate"], "reason": "Not for customers in Account customers."})

    def test_a_group_with_no_rule_takes_the_nearest_rule_above_it(self):
        self.assertEqual(check(group="Gold accounts")["exclude_tenders"], ["Gift Certificate"])    # Account customers' rule
        self.assertEqual(check(group="Retail")["exclude_tenders"], ["On Account"])                 # the root's rule

    def test_the_nearest_rule_wins_over_one_further_up(self):
        out = check(group="Contractors")                      # under Account customers, under All Customer Groups
        self.assertNotIn("On Account", out["exclude_tenders"])
        self.assertEqual(payrules.deciding("Contractors", RULES, TREE)[0], "Account customers")

    def test_no_rule_up_the_tree_keeps_every_method(self):
        rules = payrules.rules_of([r for r in RECORDS if r["customer_group"] != "All Customer Groups"])
        self.assertEqual(payrules.on_check(context(group="Retail"), rules, TREE), {"verdict": "allow"})

    def test_a_rule_that_leaves_out_nothing_offered_is_a_plain_allow(self):
        self.assertEqual(check(group="Retail", offered=["Cash", "Credit Card"]), {"verdict": "allow"})

    def test_a_rule_that_leaves_out_every_offered_method_refuses_the_sale_in_words(self):
        out = check(group="Talabat", offered=["Cash", "Credit Card"])
        self.assertEqual(out, {"verdict": "refuse", "reason": "Customers in Talabat can't pay at this till: use one with Talabat."})
        out = check(group="Retail", offered=["On Account"])
        self.assertEqual(out["verdict"], "refuse")
        self.assertTrue(out["reason"].endswith("use one with another payment method."))

    def test_only_the_offered_methods_are_left_out_in_the_tills_order(self):
        out = check(group="USD customers", offered=["Card USD", "Cash", "Cash USD", "Credit Card"])
        self.assertEqual(out["exclude_tenders"], ["Cash", "Credit Card"])
        self.assertEqual(out["reason"], "Customers in USD customers pay with Card USD, Cash USD.")

    def test_a_method_offered_twice_is_named_once(self):
        self.assertEqual(check(group="Retail", offered=["Cash", "On Account", "On Account"])["exclude_tenders"], ["On Account"])

    def test_a_customer_with_no_group_takes_the_outermost_rule(self):
        for none in ("", None):
            self.assertEqual(check(group=none)["exclude_tenders"], ["On Account"])

    def test_a_group_the_tree_does_not_know_keeps_every_method_unless_it_has_its_own_rule(self):
        self.assertEqual(check(group="Walk-in, new"), {"verdict": "allow"})
        self.assertEqual(payrules.on_check(context(group="Talabat"), RULES, {})["exclude_tenders"][0], "Cash")

    def test_the_refusal_keeps_a_long_group_and_method_list_whole(self):
        group, methods = "G" * 30, ["Talabat Wallet Pay", "Talabat Card Pay", "Talabat Cash"]    # a list of 50 characters
        rules = payrules.rules_of([{"customer_group": group, "kind": ONLY, "mode_of_payment": m} for m in methods])
        out = payrules.on_check(context(group=group, offered=["Cash"]), rules, {group: (1, 2)})
        self.assertEqual(out["verdict"], "refuse")
        self.assertNotIn("…", out["reason"])
        self.assertTrue(out["reason"].endswith("use one with Talabat Card Pay, Talabat Cash, Talabat Wallet Pay."))
        full = payrules.rules_of([{"customer_group": "G" * 30, "kind": ONLY, "mode_of_payment": "M" * 58}])
        longest = payrules.on_check(context(group="G" * 30, offered=["Cash"]), full, {})["reason"]
        self.assertEqual((len(longest), "…" in longest), (140, False))       # the budget's own bound, exactly

    def test_words_that_come_out_empty_fall_back_to_the_apps_own(self):
        for words in ("\u200b", "\u200f", "<>", "\u200c\u200b"):
            rules = payrules.rules_of([{"customer_group": "Retail", "kind": BUT, "mode_of_payment": "Cash", "words": words}])
            out = payrules.on_check(context(group="Retail"), rules, TREE)
            self.assertEqual(out["reason"], "Not for customers in Retail.", repr(words))

    def test_the_marks_arabic_and_persian_text_carry_are_kept(self):
        words = "\u0645\u06cc\u200c\u062e\u0631\u06cc\u062f \u200f\u0646\u0642\u062f"
        rules = payrules.rules_of([{"customer_group": "Retail", "kind": BUT, "mode_of_payment": "Cash", "words": words}])
        self.assertEqual(payrules.on_check(context(group="Retail"), rules, TREE)["reason"], words)

    def test_a_groups_own_rule_replaces_the_rule_above_it(self):
        rules = payrules.rules_of(RECORDS + [{"customer_group": "Retail", "kind": BUT, "mode_of_payment": "Cheque"}])
        self.assertEqual(payrules.on_check(context(group="Retail"), rules, TREE), {"verdict": "allow"})   # On Account back

    def test_more_methods_to_leave_out_than_the_contract_carries_refuses(self):
        offered = ["Talabat"] + [f"M{i}" for i in range(21)]
        out = check(group="Talabat", offered=offered)
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("more payment methods than the rule", out["reason"])
        self.assertEqual(len(check(group="Talabat", offered=offered[:21])["exclude_tenders"]), 20)

    def test_a_refund_or_an_exchange_is_never_judged(self):
        self.assertEqual(check(group="Talabat", stage="return"), {"verdict": "allow"})
        self.assertEqual(check(group="Talabat", stage="return", lines=[line(1, qty=-1), line(2, "CAKE")]), {"verdict": "allow"})

    def test_every_sentence_is_plain_and_at_most_140(self):
        long = "G<b>" * 60
        rules = payrules.rules_of([{"customer_group": long, "kind": ONLY, "mode_of_payment": "X" * 90},
                                   {"customer_group": "W", "kind": BUT, "mode_of_payment": "Cash", "words": "W<i>" * 60}])
        tree = {long: (1, 2), "W": (3, 4)}
        outs = [payrules.on_check(context(group=long), rules, tree),
                payrules.on_check(context(group=long, offered=["Cash"]), rules, tree),
                payrules.on_check(context(group="W"), rules, tree),
                payrules.on_check(context(group=long, offered=["X" * 90] + [f"M{i}" for i in range(21)]), rules, tree)]
        for out in outs:
            self.assertTrue(1 <= len(out["reason"]) <= 140, out["reason"])
            self.assertFalse(set("<>") & set(out["reason"]))


class RulesOf(unittest.TestCase):
    def test_one_rule_per_group_with_every_method_row(self):
        self.assertEqual(RULES["USD customers"], {"kind": ONLY, "methods": {"Cash USD", "Card USD"}, "words": ""})
        self.assertEqual(RULES["Talabat"]["words"], "Talabat customers pay with Talabat.")

    def test_a_rule_with_no_method_row_is_kept(self):
        rules = payrules.rules_of([{"customer_group": "Retail", "kind": ONLY, "mode_of_payment": None}])
        self.assertEqual(rules, {"Retail": {"kind": ONLY, "methods": set(), "words": ""}})
        out = payrules.on_check(context(group="Retail"), rules, TREE)
        self.assertEqual(out["verdict"], "refuse")         # only these, with none listed: nothing to pay with
        self.assertTrue(out["reason"].endswith("use one with another payment method."))

    def test_a_row_without_a_group_or_with_an_unknown_kind_is_left_out(self):
        out = payrules.rules_of([{"kind": ONLY, "mode_of_payment": "Cash"}, {"customer_group": "X", "kind": "Never",
                                                                            "mode_of_payment": "Cash"}])
        self.assertEqual(out, {})

    def test_anything_but_a_list_of_records_is_refused(self):
        for bad in (None, {"data": []}, ["x"], "[]"):
            with self.assertRaises(ValueError):
                payrules.rules_of(bad)
            with self.assertRaises(ValueError):
                payrules.tree_of(bad)


class TreeOf(unittest.TestCase):
    def test_spans_are_whole_numbers(self):
        self.assertEqual(TREE["Gold accounts"], (3, 4))
        self.assertEqual(payrules.tree_of([{"name": "A", "lft": "1", "rgt": 2}, {"name": "B", "lft": True, "rgt": 2},
                                           {"name": "C", "lft": 1, "rgt": 2}]), {"C": (1, 2)})


class Context(unittest.TestCase):
    def test_a_check_is_read(self):
        ctx = context()
        self.assertIs(payrules.check_context({"point": "check/1", "context": ctx}), ctx)

    def test_a_bad_shape_is_refused_before_any_decision(self):
        for bad in ({"point": "capture/1", "context": context()}, {"point": "check/1", "context": {}},
                    {"point": "check/1", "context": dict(context(), offered_tenders="Cash")},
                    {"point": "check/1", "context": dict(context(), offered_tenders=[1])},
                    {"point": "check/1", "context": dict(context(), customer_group=5)},
                    {"point": "check/1", "context": dict(context(), stage="layaway")}, []):
            with self.assertRaises(ValueError):
                payrules.check_context(bad)


class Verify(unittest.TestCase):
    def test_the_signature_and_the_time_are_checked(self):
        import base64
        import hashlib
        import hmac
        raw, ts = b'{"a":1}', "1000"
        sig = base64.b64encode(hmac.new(b"s", b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(payrules.verify(ts, sig, raw, "s", now=1000), "")
        self.assertTrue(payrules.verify(ts, sig, raw, "t", now=1000))
        self.assertTrue(payrules.verify(ts, sig, raw, "s", now=1000 + 301))
        self.assertTrue(payrules.verify(None, sig, raw, "s", now=1000))
        self.assertTrue(payrules.verify("9" * 5000, sig, raw, "s", now=1000))    # never int() on a long digit string


if __name__ == "__main__":
    unittest.main()
