"""S48's rules (``codecheck.on_select``, ``codecheck.on_verify``, ``codecheck.deciding``, ``codecheck.rules_of``,
``codecheck.capture_context``): a customer of a group whose deciding rule asks gets a code to the number on their record,
the nearest rule up the tree decides, a right code is good once and for ten minutes, and every sentence is plain text the
till accepts.

    python3 -m unittest discover -s samples/s48_customer_code_check/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import codecheck  # noqa: E402

RECORDS = [
    {"name": "Members", "customer_group": "Members", "ask": "Ask for a code", "without_mobile": "Take them off the sale", "words": None},
    {"name": "Staff members", "customer_group": "Staff members", "ask": "Never ask", "without_mobile": None, "words": ""},
    {"name": "Trade", "customer_group": "Trade", "ask": "Ask for a code", "without_mobile": "Let them on",
     "words": "Ask the buyer for the code we texted."},
]
# All Customer Groups (1, 14) > Members (2, 7) > Gold members (3, 4) · Staff members (5, 6)
#                             > Retail (8, 9) · Trade (10, 11) · Walk-in (12, 13)
TREE_ROWS = [{"name": "All Customer Groups", "lft": 1, "rgt": 14}, {"name": "Members", "lft": 2, "rgt": 7},
             {"name": "Gold members", "lft": 3, "rgt": 4}, {"name": "Staff members", "lft": 5, "rgt": 6},
             {"name": "Retail", "lft": 8, "rgt": 9}, {"name": "Trade", "lft": 10, "rgt": 11},
             {"name": "Walk-in", "lft": 12, "rgt": 13}]
CHALLENGE = "7a1e" + "0" * 28


def context(group="Members", phone="+20 100 555 0147", customer="CUST-1", profile="Cairo Tills", operator="c@shop.example"):
    return {"v": 1, "point": "capture", "event": "customer_select", "challenge_id": CHALLENGE, "sale_ref": "sale-1",
            "store": "Cairo - MP", "pos_profile": profile, "operator": operator, "lang": "en",
            "customer": {"customer": customer, "customer_name": "Mona Adel", "phone": phone,
                         "email": "mona@example.com", "customer_group": group}}


def code_ctx(code="482913"):
    return {"v": 1, "point": "capture", "event": "verify", "challenge_id": CHALLENGE, "code": code}


RULES, TREE = codecheck.rules_of(RECORDS), codecheck.tree_of(TREE_ROWS)


def select(**kw):
    return codecheck.on_select(context(**kw), RULES, TREE)


class Select(unittest.TestCase):
    def test_a_group_whose_rule_asks_gets_a_code_named_by_its_last_two_digits(self):
        self.assertEqual(select(group="Members"), {
            "verdict": "challenge", "length": 6,
            "prompt": "Ask the customer for the 6-digit code we sent to their phone ending 47."})

    def test_a_group_with_no_rule_takes_the_nearest_rule_above_it(self):
        self.assertEqual(select(group="Gold members")["verdict"], "challenge")

    def test_never_ask_lets_a_group_below_off_the_code(self):
        self.assertEqual(select(group="Staff members"), {"verdict": "allow"})

    def test_no_rule_up_the_tree_is_never_asked(self):
        self.assertEqual(select(group="Retail"), {"verdict": "allow"})

    def test_the_rules_own_words_go_with_the_code_field(self):
        self.assertEqual(select(group="Trade")["prompt"], "Ask the buyer for the code we texted.")

    def test_no_mobile_number_takes_the_customer_off_where_the_rule_says(self):
        for phone in ("", "  ", "+20 1"):
            self.assertEqual(select(group="Members", phone=phone), {
                "verdict": "refuse", "reason": "Customers in Members need a code, and this customer has no mobile number."})

    def test_no_mobile_number_lets_the_customer_on_where_the_rule_says(self):
        self.assertEqual(select(group="Trade", phone=""), {"verdict": "allow"})

    def test_a_number_is_the_first_one_the_record_holds_in_the_shops_phone_shape(self):
        for raw, want in (("+971 50 123 4567 / +971 4 123 4567", "+971 50 123 4567"), ("0100 555 0147 ext 2", "0100 555 0147"),
                          ("+44 (0) 7700 900 123 x", "+44 (0) 7700 900 123"), ("+20 100 555 0147 000 000 11", ""),
                          ("  +20-100-555-0147  ", "+20-100-555-0147"), ("12345", ""), ("ext 2", ""), ("", ""),
                          ("+1 234 567 890 123 456 789 0123", "")):
            self.assertEqual(codecheck.mobile_of(raw), want, raw)
        self.assertEqual(select(group="Members", phone="+20 100 555 0147 / 0100")["prompt"][-3:], "47.")

    def test_a_record_whose_phone_holds_no_number_is_no_mobile(self):
        self.assertEqual(select(group="Members", phone="ask at desk")["verdict"], "refuse")

    def test_a_customer_with_no_group_takes_the_outermost_rule(self):
        rules = codecheck.rules_of(RECORDS + [{"customer_group": "All Customer Groups", "ask": "Ask for a code"}])
        self.assertEqual(codecheck.on_select(context(group=""), rules, TREE)["verdict"], "challenge")
        self.assertEqual(select(group=""), {"verdict": "allow"})

    def test_a_group_the_tree_does_not_know_is_unreadable_while_the_shop_has_rules(self):
        with self.assertRaises(ValueError):
            select(group="Made a minute ago")
        self.assertEqual(codecheck.on_select(context(group="Made a minute ago"), {}, TREE), {"verdict": "allow"})

    def test_a_value_the_form_never_writes_errs_on_the_side_of_the_code(self):
        rules = codecheck.rules_of([{"customer_group": "Retail", "ask": "Sometimes", "without_mobile": "Maybe"}])
        self.assertTrue(rules["Retail"]["ask"])
        self.assertFalse(rules["Retail"]["let_on"])

    def test_every_sentence_is_plain_and_at_most_140(self):
        long = "<G>" * 80
        rules = codecheck.rules_of([{"customer_group": long, "ask": "Ask for a code", "words": "<b>" + "w" * 300}])
        tree = {long: (1, 2)}
        a = codecheck.on_select(context(group=long), rules, tree)
        b = codecheck.on_select(context(group=long, phone=""), rules, tree)
        for s in (a["prompt"], b["reason"]):
            self.assertLessEqual(len(s), 140)
            self.assertNotIn("<", s)
            self.assertNotIn(">", s)

    def test_words_that_come_out_empty_fall_back_to_the_apps_own(self):
        rules = codecheck.rules_of([{"customer_group": "Retail", "ask": "Ask for a code", "words": "<>‌"}])
        self.assertTrue(codecheck.on_select(context(group="Retail"), rules, TREE)["prompt"].startswith("Ask the customer"))


class Verify(unittest.TestCase):
    NOW = 1_000_000

    def record(self, **kw):
        return dict({"name": CHALLENGE, "code": "482913", "status": "Sent", "sent_at": self.NOW - 60}, **kw)

    def test_the_right_code_is_ok(self):
        self.assertEqual(codecheck.on_verify(code_ctx(), self.record(), self.NOW), {"verdict": "ok"})

    def test_a_wrong_code_is_refused_in_words(self):
        self.assertEqual(codecheck.on_verify(code_ctx("482914"), self.record(), self.NOW),
                         {"verdict": "refuse", "reason": codecheck.WRONG})

    def test_a_used_an_old_or_a_missing_code_has_ended(self):
        ended = {"verdict": "refuse", "reason": codecheck.ENDED}
        for rec in (self.record(status="Used"), self.record(status="Used", code=""), self.record(sent_at=self.NOW - 601),
                    self.record(sent_at=self.NOW + 5), self.record(code=""), self.record(code=None), self.record(sent_at=None),
                    self.record(sent_at=True), None):
            self.assertEqual(codecheck.on_verify(code_ctx(), rec, self.NOW), ended, rec)

    def test_ten_minutes_is_still_good(self):
        self.assertEqual(codecheck.on_verify(code_ctx(), self.record(sent_at=self.NOW - 600), self.NOW), {"verdict": "ok"})


class Codes(unittest.TestCase):
    def test_a_code_is_six_digits_from_a_secure_source(self):
        codes = {codecheck.new_code() for _ in range(200)}
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))
        self.assertGreater(len(codes), 190)

    def test_the_record_holds_what_the_notification_and_the_next_pick_read(self):
        rec = codecheck.code_record(context(), "004213", 1234.9)
        self.assertEqual(rec, {"challenge": CHALLENGE, "customer": "CUST-1", "customer_name": "Mona Adel",
                               "mobile": "+20 100 555 0147", "code": "004213", "store": "Cairo - MP",
                               "pos_profile": "Cairo Tills", "operator": "c@shop.example", "status": "Sent", "sent_at": 1234})


class RulesOf(unittest.TestCase):
    def test_a_row_with_no_group_is_left_out(self):
        self.assertEqual(codecheck.rules_of([{"customer_group": None, "ask": "Ask for a code"}, {"ask": "Never ask"}]), {})

    def test_anything_but_records_is_unreadable(self):
        for bad in (None, {}, [1], "x"):
            with self.assertRaises(ValueError):
                codecheck.rules_of(bad)
            with self.assertRaises(ValueError):
                codecheck.tree_of(bad)


class Context(unittest.TestCase):
    def test_a_select_and_a_verify_are_read(self):
        self.assertEqual(codecheck.capture_context({"point": "capture/1", "context": context()})["event"], "customer_select")
        self.assertEqual(codecheck.capture_context({"point": "capture/1", "context": code_ctx()})["code"], "482913")

    def test_a_bad_shape_is_refused_before_any_decision(self):
        bad = [{}, {"point": "check/1", "context": context()},
               {"point": "capture/1", "context": dict(context(), event="customer_add")},
               {"point": "capture/1", "context": dict(context(), challenge_id="short")},
               {"point": "capture/1", "context": dict(context(), customer=dict(context()["customer"], customer_group=None))},
               {"point": "capture/1", "context": dict(context(), customer=dict(context()["customer"], phone=None))},
               {"point": "capture/1", "context": dict(context(), customer=dict(context()["customer"], customer=""))},
               {"point": "capture/1", "context": dict(context(), operator=None)},
               {"point": "capture/1", "context": code_ctx("12")},
               {"point": "capture/1", "context": code_ctx("12 456")},
               {"point": "capture/1", "context": code_ctx("١٢٣٤٥٦")}]
        for body in bad:
            with self.assertRaises(ValueError, msg=body):
                codecheck.capture_context(body)


class Signature(unittest.TestCase):
    def test_the_signature_and_the_time_are_checked(self):
        import base64
        import hashlib
        import hmac
        raw, ts = b'{"a":1}', "1000"
        sig = base64.b64encode(hmac.new(b"s", b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(codecheck.verify(ts, sig, raw, "s", now=1000), "")
        self.assertTrue(codecheck.verify(ts, sig, raw, "t", now=1000))
        self.assertTrue(codecheck.verify(ts, sig, raw, "s", now=1000 + 301))
        self.assertTrue(codecheck.verify(None, sig, raw, "s", now=1000))
        self.assertTrue(codecheck.verify("9" * 5000, sig, raw, "s", now=1000))    # never int() on a long digit string


if __name__ == "__main__":
    unittest.main()
