"""S49's pure core: the rule, which sales are asked, the contact, the signed link, the page and the answers.

    python3 -m unittest discover -s samples/s49_post_sale_feedback/tests -p 'test_*.py'
"""

import datetime
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import feedback as fb  # noqa: E402

TODAY = datetime.date(2026, 10, 24)


def rule(**k):
    r = {"name": "R", "enabled": 1, "shown_name": "Al Waha", "look_back_days": 1, "open_days": 7, "profiles": []}
    r.update(k)
    return fb.rule_of(r)


def sale(name, customer, day="2026-10-24", **k):
    s = {"name": name, "customer": customer, "posting_date": day, "docstatus": 1, "is_return": 0,
         "contact_mobile": "+971501234567", "pos_profile": "A", "creation": f"{day} 10:00:00"}
    s.update(k)
    return s


class Rules(unittest.TestCase):
    def test_a_rule_is_read_with_its_defaults_or_named_in_a_sentence(self):
        r = rule(question="", answer_good="", profiles=["B", "A", "A", None])
        self.assertEqual((r.question, r.answers, r.look_back, r.open_days, r.profiles),
                         (fb.DEFAULT_QUESTION, ["Satisfied", "Neutral", "Not satisfied"], 1, 7, ["A", "B"]))
        self.assertEqual(rule(look_back_days=None, open_days="").look_back, 1)
        for bad in ({"enabled": 0}, {"shown_name": "  "}, {"look_back_days": 8}, {"look_back_days": True},
                    {"open_days": 31}, {"open_days": 2.5}):
            self.assertIsInstance(rule(**bad), str, bad)

    def test_the_list_read_gives_one_row_per_pos_profile(self):
        rows = [{"name": "R", "pos_profile": "A"}, {"name": "R", "pos_profile": "B"}, {"name": "S", "pos_profile": None}]
        got = fb.rules_from_rows(rows)
        self.assertEqual((got["R"]["profiles"], got["S"]["profiles"]), (["A", "B"], []))

    def test_one_day_back_reaches_yesterday_and_today(self):
        self.assertEqual(fb.since(rule(), TODAY), datetime.date(2026, 10, 23))
        self.assertEqual(fb.since(rule(look_back_days=7), TODAY), datetime.date(2026, 10, 17))


class Choose(unittest.TestCase):
    def test_only_the_rules_tills_and_days_and_never_a_walk_in_a_return_or_no_customer(self):
        r = rule(profiles=["A"])
        sales = [sale("S1", "C1"), sale("S2", "C2", pos_profile="B"), sale("S3", "C3", day="2026-10-22"),
                 sale("S4", "W"), sale("S5", "C5", is_return=1), sale("S6", None), sale("S7", "C7", docstatus=0),
                 sale("S8", "C8", day="2026-10-25")]          # ahead of UTC's day (a store east of UTC): asked
        chosen, counts = fb.choose(sales, r, {"W"}, set(), set(), {}, set(), TODAY)
        self.assertEqual([c[0]["name"] for c in chosen], ["S1", "S8"])
        self.assertEqual(counts, {"no_contact": 0, "stopped": 0, "asked": 0})

    def test_a_customer_is_asked_once_their_latest_sale(self):
        chosen, _ = fb.choose([sale("S1", "C1"), sale("S2", "C1")], rule(), set(), set(), set(), {}, set(), TODAY)
        self.assertEqual([c[0]["name"] for c in chosen], ["S2"])

    def test_already_asked_stopped_and_no_contact_are_counted(self):
        sales = [sale("S1", "C1"), sale("S2", "C2"), sale("S3", "C3", contact_mobile=""), sale("S4", "C4")]
        chosen, counts = fb.choose(sales, rule(), set(), {"S1", "C4"}, {"C2"}, {}, set(), TODAY)
        self.assertEqual(chosen, [])
        self.assertEqual(counts, {"no_contact": 1, "stopped": 1, "asked": 2})

    def test_the_customers_own_contact_when_the_sale_has_none(self):
        s = sale("S1", "C1", contact_mobile="", contact_email="")
        contacts = fb.contacts_of([{"name": "C1", "mobile_no": "0501111111", "custom_phone_no": "+971 55 222 3333",
                                    "email_id": "a@b.co"}])
        chosen, _ = fb.choose([s], rule(), set(), set(), set(), contacts, set(), TODAY)
        self.assertEqual(chosen[0][1:], ("+971 55 222 3333", "a@b.co"))     # the till's phone field first

    def test_a_customer_taken_by_another_rule_of_the_press_is_asked_by_that_rule_only(self):
        taken = {"C1"}
        chosen, counts = fb.choose([sale("S1", "C1")], rule(), set(), set(), set(), {}, taken, TODAY)
        self.assertEqual((chosen, counts["asked"]), ([], 1))

    def test_the_next_press_starts_at_the_first_sale_not_made_or_after_the_last_read(self):
        r = rule(asked_up_to="2026-10-24 09:00:00")
        sales = [sale("S1", "C1", creation="2026-10-24 10:00:00"), sale("S2", "C2", creation="2026-10-24 11:00:00")]
        self.assertEqual(fb.mark_after(r, sales, []), "2026-10-24 11:00:00")
        self.assertEqual(fb.mark_after(r, sales, [sales[1], sales[0]]), "2026-10-24 10:00:00")
        self.assertEqual(fb.mark_after(r, [], []), "2026-10-24 09:00:00")


class Contact(unittest.TestCase):
    def test_a_phone_is_its_first_number_in_phone_characters(self):
        self.assertEqual(fb.phone_of("+971 50 123 4567 / 04 222 3333"), "+971 50 123 4567")
        self.assertEqual(fb.phone_of("tel: (050) 765-4321"), "(050) 765-4321")
        self.assertEqual(fb.phone_of("12345"), "")
        self.assertEqual(fb.phone_of(None), "")
        self.assertLessEqual(len(fb.phone_of("1" * 40)), 20)

    def test_an_email_is_one_address(self):
        self.assertEqual(fb.email_of(" a.b@shop.example "), "a.b@shop.example")
        for bad in ("a@b", "a b@c.d", "a@@b.c", "", None, "x" * 140 + "@a.bc"):
            self.assertEqual(fb.email_of(bad), "", bad)


class Link(unittest.TestCase):
    def test_a_link_opens_for_its_own_site_and_sale_and_secret_only(self):
        link = fb.link_of("https://p.example/", "shop.example", "ACC-PSINV-2026-00001", b"k1")
        self.assertTrue(link.startswith("https://p.example/#s=shop.example&t=ACC-PSINV-2026-00001."))
        token = link.split("&t=", 1)[1]
        self.assertEqual(fb.sale_of_token("shop.example", token, [b"k1"]), "ACC-PSINV-2026-00001")
        self.assertEqual(fb.sale_of_token("shop.example", token, [b"k2", b"k1"]), "ACC-PSINV-2026-00001")
        self.assertIsNone(fb.sale_of_token("other.example", token, [b"k1"]))
        self.assertIsNone(fb.sale_of_token("shop.example", token, [b"k2"]))
        self.assertIsNone(fb.sale_of_token("shop.example", token.replace("00001", "00002"), [b"k1"]))
        self.assertIsNone(fb.sale_of_token("shop.example", token[:-1], [b"k1"]))
        self.assertIsNone(fb.sale_of_token("shop.example", 7, [b"k1"]))

    def test_the_request_carries_the_sale_and_its_last_day(self):
        req = fb.request_of(sale("S1", "C1", customer_name="  A   B "), rule(open_days=3), "+971", "", "DXB", "L")
        self.assertEqual((req["sale"], req["customer_name"], req["sale_date"], req["open_until"], req["status"]),
                         ("S1", "A B", "2026-10-24", "2026-10-27", "Sent"))


class Page(unittest.TestCase):
    REQ = {"sale_date": "2026-10-24", "open_until": "2026-10-31", "rule": "R"}

    def test_open_then_answered_then_closed(self):
        r = {"shown_name": "Al Waha", "question": "Q?", "answer_good": "Yes"}
        self.assertEqual(fb.page_of(self.REQ, r, TODAY)["state"], "open")
        self.assertEqual(fb.page_of(dict(self.REQ, answer="Neutral"), r, TODAY)["state"], "answered")
        self.assertEqual(fb.page_of(self.REQ, r, datetime.date(2026, 11, 1))["state"], "closed")
        self.assertEqual(fb.page_of(dict(self.REQ, open_until=None), r, TODAY)["state"], "closed")
        self.assertEqual(fb.page_of(self.REQ, r, TODAY)["answers"], ["Yes", "Neutral", "Not satisfied"])

    def test_a_rule_switched_off_since_still_shows_its_words_and_a_deleted_one_the_apps(self):
        self.assertEqual(fb.page_of(self.REQ, {"enabled": 0, "shown_name": "Al Waha"}, TODAY)["name"], "Al Waha")
        self.assertEqual(fb.page_of(self.REQ, {}, TODAY)["question"], fb.DEFAULT_QUESTION)

    def test_an_answer_is_one_of_three_or_stop_alone(self):
        self.assertEqual(fb.answer_of({"answer": 1, "comment": " a  b ", "stop": True}), (1, "a b", True))
        self.assertEqual(fb.answer_of({"stop": True}), (None, "", True))
        self.assertEqual(len(fb.answer_of({"answer": 0, "comment": "x" * 900})[1]), fb.COMMENT_MAX)
        for bad in ({}, {"answer": 3}, {"answer": False}, {"answer": "1"}, {"answer": 0, "stop": "yes"}, [], None):
            with self.assertRaises(ValueError):
                fb.answer_of(bad)


class Answers(unittest.TestCase):
    def test_every_press_answer_fits_and_says_why(self):
        a = fb.press_answer(1, {"asked": 2, "stopped": 0, "no_contact": 3}, 0, False, [])
        self.assertEqual(a["message"]["body"],
                         "Made 1 feedback request. Not asked: 2 already asked, 3 with no mobile number or e-mail.")
        self.assertEqual(a["message"]["level"], "success")
        a = fb.press_answer(0, {}, 2, True, ["X was not found."] * 40)
        self.assertLessEqual(len(a["message"]["body"]), 280)
        self.assertEqual(a["message"]["level"], "warning")


if __name__ == "__main__":
    unittest.main()
