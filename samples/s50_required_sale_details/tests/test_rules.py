"""S50's rules (``details.on_check``, ``details.missing``, ``details.deciding``, ``details.rules_of``, ``details.tree_of``,
``details.check_context``): a sale whose customer's group needs a detail left empty is refused, naming it; the nearest rule
up the tree decides; a rule holds only at its POS Profiles; a refund is never judged; and every sentence is plain text the
till accepts.

    python3 -m unittest discover -s samples/s50_required_sale_details/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import details  # noqa: E402

PO, PROJECT, POLICY, MOBILE = "Purchase order number", "Project", "Policy number", "Mobile number"

# the retailer's list read: one row per detail and POS Profile (a left join; a rule with neither comes once with none)
RECORDS = [
    {"name": "Account customers", "customer_group": "Account customers", "words": None, "sale_attribute": PO, "pos_profile": None},
    {"name": "Contractors", "customer_group": "Contractors", "words": "", "sale_attribute": PO, "pos_profile": "Trade Counter"},
    {"name": "Contractors", "customer_group": "Contractors", "words": "", "sale_attribute": PROJECT, "pos_profile": "Trade Counter"},
    {"name": "Insured", "customer_group": "Insured", "words": "Insured patients give their policy number.",
     "sale_attribute": POLICY, "pos_profile": None},
    {"name": "Staff", "customer_group": "Staff", "words": None, "sale_attribute": None, "pos_profile": None},
]
# All Customer Groups (1, 16) > Account customers (2, 7) > Gold accounts (3, 4) · Contractors (5, 6)
#                             > Retail (8, 9) · Insured (10, 11) · Walk-in (12, 13) · Staff (14, 15)
TREE_ROWS = [{"name": "All Customer Groups", "lft": 1, "rgt": 16}, {"name": "Account customers", "lft": 2, "rgt": 7},
             {"name": "Gold accounts", "lft": 3, "rgt": 4}, {"name": "Contractors", "lft": 5, "rgt": 6},
             {"name": "Retail", "lft": 8, "rgt": 9}, {"name": "Insured", "lft": 10, "rgt": 11},
             {"name": "Walk-in", "lft": 12, "rgt": 13}, {"name": "Staff", "lft": 14, "rgt": 15}]


def line(n=1, code="CEMENT", qty=1, rate=1250):
    return {"line_no": n, "item_code": code, "item_group": "Building", "qty_milli": round(qty * 1000), "uom": "Nos",
            "rate_minor": rate, "amount_minor": round(rate * qty), "discount_minor": 0, "line_attributes": []}


def context(group="Account customers", customer="CUST-1", attrs=None, profile="Main Counter", stage="sale", lines=None):
    lines = lines if lines is not None else [line()]
    grand = sum(x["amount_minor"] for x in lines)
    ctx = {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "s-1", "store": "Main - S",
           "pos_profile": profile, "company": "Retailer", "currency": "AED", "lang": "en", "operator": "c@retailer.example",
           "customer": customer, "customer_group": group, "price_list": "Standard Selling", "coupon_codes": [],
           "sale_attributes": [{"name": k, "value": v} for k, v in (attrs or {}).items()], "lines": lines,
           "totals": {"net_minor": grand, "tax_minor": 0, "discount_minor": 0, "grand_minor": grand},
           "offered_tenders": ["Cash", "Credit Card", "On Account"], "pos_opening": "POS-OPE-1",
           "pos_terminal": "Main Counter 2"}
    if stage == "return":
        ctx["return_of"] = {"invoice": "SINV-1", "channel": "pos", "paid_by": ["Cash"]}
    return ctx


RULES, TREE = details.rules_of(RECORDS), details.tree_of(TREE_ROWS)


def check(**kw):
    return details.on_check(context(**kw), RULES, TREE)


class Rules(unittest.TestCase):
    def test_a_needed_detail_left_empty_refuses_the_sale_naming_it(self):
        self.assertEqual(check(), {"verdict": "refuse", "reason": "Customers in Account customers need Purchase order number. "
                                                                  "Fill in the sale's details, then Pay."})

    def test_every_needed_detail_filled_allows_the_sale(self):
        self.assertEqual(check(attrs={PO: "PO-4471"}), {"verdict": "allow"})

    def test_a_blank_value_counts_as_empty(self):
        for blank in ("", "   ", "‏", None):
            self.assertEqual(check(attrs={PO: blank})["verdict"], "refuse", repr(blank))

    def test_a_detail_the_rule_does_not_name_changes_nothing(self):
        self.assertEqual(check(attrs={PROJECT: "Tower B"})["verdict"], "refuse")
        self.assertEqual(check(attrs={PO: "PO-1", PROJECT: ""}), {"verdict": "allow"})

    def test_a_group_with_no_rule_takes_the_nearest_rule_above_it(self):
        self.assertEqual(check(group="Gold accounts")["verdict"], "refuse")               # Account customers' rule
        self.assertEqual(details.deciding("Gold accounts", RULES, TREE)[0], "Account customers")
        self.assertEqual(check(group="Retail", profile="Trade Counter"), {"verdict": "allow"})   # never a group beside it

    def test_the_nearest_rule_wins_and_replaces_the_one_above_it(self):
        rules = details.rules_of(RECORDS + [{"customer_group": "All Customer Groups", "sale_attribute": MOBILE}])
        out = details.on_check(context(group="Gold accounts"), rules, TREE)       # Account customers', not the root's
        self.assertEqual(out["reason"], "Customers in Account customers need Purchase order number. Fill in the sale's details, then Pay.")
        out = check(group="Contractors", profile="Trade Counter", attrs={PROJECT: "Tower B"})
        self.assertEqual(out["reason"], "Customers in Contractors need Purchase order number. Fill in the sale's details, then Pay.")
        self.assertEqual(check(group="Contractors", profile="Trade Counter", attrs={PO: "PO-1", PROJECT: "Tower B"}),
                         {"verdict": "allow"})

    def test_a_rule_holds_only_at_its_pos_profiles(self):
        self.assertEqual(check(group="Contractors", profile="Main Counter"), {"verdict": "allow"})
        self.assertEqual(check(group="Contractors", profile="Trade Counter")["verdict"], "refuse")

    def test_every_missing_detail_is_named_in_the_rules_order(self):
        out = check(group="Contractors", profile="Trade Counter")
        self.assertIn("need Purchase order number, Project.", out["reason"])

    def test_a_rule_with_no_detail_lets_its_group_off_the_rule_above(self):
        rules = details.rules_of(RECORDS + [{"customer_group": "All Customer Groups", "sale_attribute": MOBILE}])
        self.assertEqual(details.on_check(context(group="Staff"), rules, TREE), {"verdict": "allow"})
        self.assertEqual(details.on_check(context(group="Walk-in"), rules, TREE)["verdict"], "refuse")   # the walk-in asked

    def test_the_retailers_own_words_are_shown(self):
        self.assertEqual(check(group="Insured"), {"verdict": "refuse", "reason": "Insured patients give their policy number."})

    def test_no_rule_up_the_tree_allows(self):
        self.assertEqual(check(group="Retail"), {"verdict": "allow"})
        self.assertEqual(check(group="Walk-in, new"), {"verdict": "allow"})        # a group the tree does not know

    def test_a_customer_with_no_group_takes_the_outermost_rule(self):
        rules = details.rules_of([{"customer_group": "All Customer Groups", "sale_attribute": MOBILE}])
        for none in ("", None):
            self.assertEqual(details.on_check(context(group=none), rules, TREE)["verdict"], "refuse")

    def test_a_refund_or_an_exchanges_returned_lines_are_never_judged(self):
        self.assertEqual(check(stage="return"), {"verdict": "allow"})
        self.assertEqual(check(stage="return", lines=[line(1, qty=-1), line(2, "SAND")]), {"verdict": "allow"})

    def test_words_that_come_out_empty_fall_back_to_the_apps_own(self):
        for words in ("​", "‏", "<>", "‌​"):
            rules = details.rules_of([{"customer_group": "Retail", "sale_attribute": PO, "words": words}])
            self.assertTrue(details.on_check(context(group="Retail"), rules, TREE)["reason"].startswith("Customers in Retail"),
                            repr(words))

    def test_the_marks_arabic_and_persian_text_carry_are_kept(self):
        words = "می‌خرید ‏نقد"
        rules = details.rules_of([{"customer_group": "Retail", "sale_attribute": PO, "words": words}])
        self.assertEqual(details.on_check(context(group="Retail"), rules, TREE)["reason"], words)

    def test_every_sentence_is_plain_and_at_most_140(self):
        long = "G<b>" * 60
        rules = details.rules_of([{"customer_group": long, "sale_attribute": f"D{i} " + "x" * 30} for i in range(5)]
                                 + [{"customer_group": "W", "sale_attribute": PO, "words": "W<i>" * 60}])
        for group in (long, "W"):
            out = details.on_check(context(group=group), rules, {long: (1, 2), "W": (3, 4)})
            self.assertEqual(out["verdict"], "refuse")
            self.assertTrue(1 <= len(out["reason"]) <= 140, out["reason"])
            self.assertFalse(set("<>") & set(out["reason"]))
        full = details.rules_of([{"customer_group": "G" * 30, "sale_attribute": "D" * 52}])
        longest = details.on_check(context(group="G" * 30), full, {})["reason"]
        self.assertEqual((len(longest), "…" in longest), (140, False))       # the budget's own bound, exactly
        over = details.rules_of([{"customer_group": "G" * 30, "sale_attribute": "D" * 70}])
        cut = details.on_check(context(group="G" * 30), over, {})["reason"]     # a long list is cut, never the instruction
        self.assertTrue(cut.endswith("Fill in the sale's details, then Pay.") and len(cut) <= 140, cut)


class Missing(unittest.TestCase):
    def test_only_the_rules_details_not_filled(self):
        rule = {"details": [PO, PROJECT], "profiles": set(), "words": ""}
        self.assertEqual(details.missing(context(attrs={PROJECT: "x"}), rule), [PO])
        self.assertEqual(details.missing(context(attrs={PO: "1", PROJECT: "x"}), rule), [])


class RulesOf(unittest.TestCase):
    def test_one_rule_per_group_with_every_detail_and_profile(self):
        self.assertEqual(RULES["Contractors"], {"details": [PO, PROJECT], "profiles": {"Trade Counter"}, "words": ""})
        self.assertEqual(RULES["Account customers"]["profiles"], set())
        self.assertEqual(RULES["Insured"]["words"], "Insured patients give their policy number.")

    def test_a_detail_repeated_by_the_join_is_kept_once(self):
        rows = [{"customer_group": "A", "sale_attribute": PO, "pos_profile": p} for p in ("X", "Y", "Z")]
        self.assertEqual(details.rules_of(rows)["A"], {"details": [PO], "profiles": {"X", "Y", "Z"}, "words": ""})

    def test_a_rule_with_no_detail_or_profile_is_kept(self):
        self.assertEqual(RULES["Staff"], {"details": [], "profiles": set(), "words": ""})

    def test_a_row_without_a_group_is_left_out(self):
        self.assertEqual(details.rules_of([{"sale_attribute": PO}, {"customer_group": "", "sale_attribute": PO}]), {})

    def test_anything_but_a_list_of_records_is_refused(self):
        for bad in (None, {"data": []}, ["x"], "[]"):
            with self.assertRaises(ValueError):
                details.rules_of(bad)
            with self.assertRaises(ValueError):
                details.tree_of(bad)


class TreeOf(unittest.TestCase):
    def test_spans_are_whole_numbers(self):
        self.assertEqual(TREE["Gold accounts"], (3, 4))
        self.assertEqual(details.tree_of([{"name": "A", "lft": "1", "rgt": 2}, {"name": "B", "lft": True, "rgt": 2},
                                          {"name": "C", "lft": 1, "rgt": 2}]), {"C": (1, 2)})


class Context(unittest.TestCase):
    def test_a_check_is_read(self):
        ctx = context()
        self.assertIs(details.check_context({"point": "check/1", "context": ctx}), ctx)

    def test_no_sale_details_reads_as_none_filled(self):
        ctx = dict(context())
        del ctx["sale_attributes"]
        self.assertEqual(details.check_context({"point": "check/1", "context": ctx})["sale_attributes"], [])

    def test_a_bad_shape_is_refused_before_any_decision(self):
        for bad in ({"point": "capture/1", "context": context()}, {"point": "check/1", "context": {}},
                    {"point": "check/1", "context": dict(context(), sale_attributes="PO")},
                    {"point": "check/1", "context": dict(context(), sale_attributes=[{"value": "x"}])},
                    {"point": "check/1", "context": dict(context(), sale_attributes=[{"name": PO, "value": 5}])},
                    {"point": "check/1", "context": dict(context(), customer_group=5)},
                    {"point": "check/1", "context": dict(context(), pos_profile=["X"])},
                    {"point": "check/1", "context": dict(context(), stage="layaway")}, []):
            with self.assertRaises(ValueError):
                details.check_context(bad)


class Verify(unittest.TestCase):
    def test_the_signature_and_the_time_are_checked(self):
        import base64
        import hashlib
        import hmac
        raw, ts = b'{"a":1}', "1000"
        sig = base64.b64encode(hmac.new(b"s", b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(details.verify(ts, sig, raw, "s", now=1000), "")
        self.assertTrue(details.verify(ts, sig, raw, "t", now=1000))
        self.assertTrue(details.verify(ts, sig, raw, "s", now=1000 + 301))
        self.assertTrue(details.verify(None, sig, raw, "s", now=1000))
        self.assertTrue(details.verify("9" * 5000, sig, raw, "s", now=1000))    # never int() on a long digit string


if __name__ == "__main__":
    unittest.main()
