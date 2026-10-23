"""S47's rules (``storerules.on_select``, ``storerules.deciding``, ``storerules.rules_of``, ``storerules.tree_of``,
``storerules.select_context``): a customer stays on the sale only at a place their deciding rule names, the nearest rule up
the tree decides, a rule that names nowhere stops its group, and every sentence is plain text the till accepts.

    python3 -m unittest discover -s samples/s47_customers_by_store/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import storerules  # noqa: E402

# the shop's list read: one row per place (a rule with no place row comes once with none, a left join)
RECORDS = [
    {"name": "Trade accounts", "customer_group": "Trade accounts", "words": None, "store": "Sandton - CL", "pos_profile": None},
    {"name": "Trade accounts", "customer_group": "Trade accounts", "words": None, "store": "Harare - CL",
     "pos_profile": "Harare Trade Counter"},
    {"name": "Staff", "customer_group": "Staff", "words": "Staff buy at the staff shop.", "store": None,
     "pos_profile": "Staff Shop"},
    {"name": "Blocked", "customer_group": "Blocked", "words": "", "store": None, "pos_profile": None},
]
# All Customer Groups (1, 14) > Trade accounts (2, 7) > Gold trade (3, 4) · Contractors (5, 6)
#                             > Retail (8, 9) · Staff (10, 11) · Blocked (12, 13)
TREE_ROWS = [{"name": "All Customer Groups", "lft": 1, "rgt": 14}, {"name": "Trade accounts", "lft": 2, "rgt": 7},
             {"name": "Gold trade", "lft": 3, "rgt": 4}, {"name": "Contractors", "lft": 5, "rgt": 6},
             {"name": "Retail", "lft": 8, "rgt": 9}, {"name": "Staff", "lft": 10, "rgt": 11},
             {"name": "Blocked", "lft": 12, "rgt": 13}]


def context(group="Retail", store="Sandton - CL", profile="Sandton Tills", customer="CUST-1"):
    return {"v": 1, "point": "capture", "event": "customer_select", "challenge_id": "7a1e" + "0" * 28, "sale_ref": "sale-1",
            "store": store, "pos_profile": profile, "operator": "c@shop.example", "lang": "en",
            "customer": {"customer": customer, "customer_name": "Ana Diaz", "phone": "+263771234567",
                         "email": "ana@example.com", "customer_group": group}}


RULES, TREE = storerules.rules_of(RECORDS), storerules.tree_of(TREE_ROWS)


def select(**kw):
    return storerules.on_select(context(**kw), RULES, TREE)


class Rules(unittest.TestCase):
    def test_a_store_the_rule_names_keeps_the_customer_on(self):
        self.assertEqual(select(group="Trade accounts", store="Sandton - CL", profile="Sandton Tills"), {"verdict": "allow"})

    def test_a_store_the_rule_does_not_name_takes_the_customer_off_in_words(self):
        self.assertEqual(select(group="Trade accounts", store="Bulawayo - CL", profile="Bulawayo Tills"), {
            "verdict": "refuse",
            "reason": "Customers in Trade accounts buy only at Harare Trade Counter at Harare - CL, Sandton - CL."})

    def test_a_place_with_both_sides_needs_that_pos_profile_at_that_store(self):
        self.assertEqual(select(group="Trade accounts", store="Harare - CL", profile="Harare Trade Counter"), {"verdict": "allow"})
        self.assertEqual(select(group="Trade accounts", store="Harare - CL", profile="Harare Tills")["verdict"], "refuse")
        self.assertEqual(select(group="Trade accounts", store="Mutare - CL", profile="Harare Trade Counter")["verdict"], "refuse")

    def test_a_pos_profile_alone_is_that_pos_profile_at_any_store(self):
        self.assertEqual(select(group="Staff", store="Harare - CL", profile="Staff Shop"), {"verdict": "allow"})
        self.assertEqual(select(group="Staff", store="Harare - CL", profile="Harare Tills"),
                         {"verdict": "refuse", "reason": "Staff buy at the staff shop."})

    def test_a_group_with_no_rule_takes_the_nearest_rule_above_it(self):
        self.assertEqual(select(group="Gold trade", store="Bulawayo - CL")["verdict"], "refuse")    # Trade accounts' rule
        self.assertEqual(select(group="Gold trade", store="Sandton - CL"), {"verdict": "allow"})
        self.assertIn("Customers in Trade accounts", select(group="Contractors", store="Bulawayo - CL")["reason"])
        self.assertEqual(select(group="Retail", store="Bulawayo - CL"), {"verdict": "allow"})   # a sibling's rule is not above it

    def test_the_nearest_rule_wins_over_one_further_up(self):
        rules = storerules.rules_of(RECORDS + [{"customer_group": "All Customer Groups", "store": "Bulawayo - CL"}])
        out = storerules.on_select(context(group="Gold trade", store="Sandton - CL"), rules, TREE)
        self.assertEqual(out, {"verdict": "allow"})                     # Trade accounts', not the root's
        self.assertEqual(storerules.deciding("Gold trade", rules, TREE)[0], "Trade accounts")

    def test_no_rule_up_the_tree_buys_anywhere(self):
        self.assertEqual(select(group="Retail", store="Bulawayo - CL"), {"verdict": "allow"})

    def test_a_groups_own_rule_replaces_the_rule_above_it(self):
        rules = storerules.rules_of(RECORDS + [{"customer_group": "Gold trade", "store": "Bulawayo - CL"}])
        self.assertEqual(storerules.on_select(context(group="Gold trade", store="Bulawayo - CL"), rules, TREE),
                         {"verdict": "allow"})
        self.assertEqual(storerules.on_select(context(group="Gold trade", store="Sandton - CL"), rules, TREE)["verdict"],
                         "refuse")                                      # the rule above no longer lets it buy there

    def test_a_rule_that_names_nowhere_stops_its_group_everywhere(self):
        for store in ("Sandton - CL", "Harare - CL", ""):
            self.assertEqual(select(group="Blocked", store=store),
                             {"verdict": "refuse", "reason": "Customers in Blocked can't buy at this store."}, store)

    def test_a_customer_with_no_group_takes_the_outermost_rule(self):
        rules = storerules.rules_of(RECORDS + [{"customer_group": "All Customer Groups", "store": "Sandton - CL"}])
        self.assertEqual(storerules.on_select(context(group="", store="Bulawayo - CL"), rules, TREE)["verdict"], "refuse")
        self.assertEqual(storerules.on_select(context(group="", store="Sandton - CL"), rules, TREE), {"verdict": "allow"})

    def test_a_group_the_tree_does_not_know_buys_anywhere_unless_it_has_its_own_rule(self):
        self.assertEqual(select(group="Walk-in, new", store="Bulawayo - CL"), {"verdict": "allow"})
        self.assertEqual(storerules.on_select(context(group="Staff", profile="Tills"), RULES, {})["verdict"], "refuse")

    def test_an_empty_store_or_pos_profile_from_the_till_never_matches_a_named_side(self):
        self.assertEqual(select(group="Trade accounts", store="", profile="")["verdict"], "refuse")
        self.assertEqual(select(group="Staff", store="Sandton - CL", profile="")["verdict"], "refuse")

    def test_words_that_come_out_empty_fall_back_to_the_apps_own(self):
        for words in ("​", "‏", "<>", "‌​"):
            rules = storerules.rules_of([{"customer_group": "Retail", "store": "A", "words": words}])
            out = storerules.on_select(context(group="Retail", store="B"), rules, TREE)
            self.assertEqual(out["reason"], "Customers in Retail buy only at A.", repr(words))

    def test_the_marks_arabic_and_persian_text_carry_are_kept(self):
        words = "فقط ‏فرع المرکز"
        rules = storerules.rules_of([{"customer_group": "Retail", "store": "A", "words": words}])
        self.assertEqual(storerules.on_select(context(group="Retail", store="B"), rules, TREE)["reason"], words)

    def test_the_refusal_keeps_a_long_group_and_place_list_whole_within_its_budget(self):
        group, places = "G" * 40, ["S" * 35, "T" * 36]           # "S…, T…" is 73 characters
        rules = storerules.rules_of([{"customer_group": group, "store": p} for p in places])
        out = storerules.on_select(context(group=group, store="Elsewhere"), rules, {group: (1, 2)})
        self.assertEqual((len(out["reason"]), "…" in out["reason"]), (140, False))
        self.assertTrue(out["reason"].endswith("T" * 36 + "."))

    def test_every_sentence_is_plain_and_at_most_140(self):
        long = "G<b>" * 60
        rules = storerules.rules_of([{"customer_group": long, "store": "X<i>" * 60},
                                     {"customer_group": "W", "store": "A", "words": "W<i>" * 60},
                                     {"customer_group": "N", "store": None}])
        tree = {long: (1, 2), "W": (3, 4), "N": (5, 6)}
        outs = [storerules.on_select(context(group=g, store="Z"), rules, tree) for g in (long, "W", "N")]
        for out in outs:
            self.assertEqual(out["verdict"], "refuse")
            self.assertTrue(1 <= len(out["reason"]) <= 140, out["reason"])
            self.assertFalse(set("<>") & set(out["reason"]))


class RulesOf(unittest.TestCase):
    def test_one_rule_per_group_with_every_place_row(self):
        self.assertEqual(RULES["Trade accounts"], {"places": {("Sandton - CL", ""), ("Harare - CL", "Harare Trade Counter")},
                                                   "words": ""})
        self.assertEqual(RULES["Staff"], {"places": {("", "Staff Shop")}, "words": "Staff buy at the staff shop."})

    def test_a_rule_with_no_place_row_is_kept_with_none(self):
        self.assertEqual(RULES["Blocked"], {"places": set(), "words": ""})

    def test_a_place_with_both_sides_blank_is_no_place(self):
        rules = storerules.rules_of([{"customer_group": "R", "store": " ", "pos_profile": ""}])
        self.assertEqual(rules, {"R": {"places": set(), "words": ""}})

    def test_a_row_without_a_group_is_left_out(self):
        self.assertEqual(storerules.rules_of([{"store": "A"}, {"customer_group": "", "store": "A"}]), {})

    def test_anything_but_a_list_of_records_is_refused(self):
        for bad in (None, {"data": []}, ["x"], "[]"):
            with self.assertRaises(ValueError):
                storerules.rules_of(bad)
            with self.assertRaises(ValueError):
                storerules.tree_of(bad)


class TreeOf(unittest.TestCase):
    def test_spans_are_whole_numbers(self):
        self.assertEqual(TREE["Gold trade"], (3, 4))
        self.assertEqual(storerules.tree_of([{"name": "A", "lft": "1", "rgt": 2}, {"name": "B", "lft": True, "rgt": 2},
                                             {"name": "C", "lft": 1, "rgt": 2}]), {"C": (1, 2)})


class Context(unittest.TestCase):
    def test_a_select_is_read(self):
        ctx = context()
        self.assertIs(storerules.select_context({"point": "capture/1", "context": ctx}), ctx)

    def test_a_bad_shape_is_refused_before_any_decision(self):
        scan = dict(context(), event="scan")
        for bad in ({"point": "check/1", "context": context()}, {"point": "capture/1", "context": {}},
                    {"point": "capture/1", "context": scan},
                    {"point": "capture/1", "context": dict(context(), v=2)},
                    {"point": "capture/1", "context": dict(context(), store=None)},
                    {"point": "capture/1", "context": dict(context(), pos_profile=5)},
                    {"point": "capture/1", "context": dict(context(), customer="CUST-1")},
                    {"point": "capture/1", "context": dict(context(), customer={"customer": "CUST-1"})}, []):
            with self.assertRaises(ValueError):
                storerules.select_context(bad)


class Verify(unittest.TestCase):
    def test_the_signature_and_the_time_are_checked(self):
        import base64
        import hashlib
        import hmac
        raw, ts = b'{"a":1}', "1000"
        sig = base64.b64encode(hmac.new(b"s", b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(storerules.verify(ts, sig, raw, "s", now=1000), "")
        self.assertTrue(storerules.verify(ts, sig, raw, "t", now=1000))
        self.assertTrue(storerules.verify(ts, sig, raw, "s", now=1000 + 301))
        self.assertTrue(storerules.verify(None, sig, raw, "s", now=1000))


if __name__ == "__main__":
    unittest.main()
