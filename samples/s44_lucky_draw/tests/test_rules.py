"""S44's core: the entries a sale gives, the customer group tree, the draw's fairness and numbering, the fingerprint and
the answers' limits.

    python3 -m unittest discover -s samples/s44_lucky_draw/tests -p 'test_*.py'
"""

import datetime
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE)]
import draw  # noqa: E402


def rules(**k):
    c = {"company": "PP Co", "from_date": "2026-10-01", "to_date": "2026-10-31", "spend_per_entry": 100}
    c.update(k)
    r = draw.rules_of(c)
    assert isinstance(r, draw.Rules), r
    return r


def s(name, customer, total, day="2026-10-02", time_="10:00:00", till="POS-A", group="All"):
    return {"name": name, "customer": customer, "base_grand_total": total, "posting_date": day, "posting_time": time_,
            "pos_profile": till, "customer_group": group}


class Entries(unittest.TestCase):
    def test_entries_are_the_net_total_divided_rounded_down(self):
        got = draw.entries_of([s("A", "C1", 399.99), s("B", "C2", 100), s("C", "C3", 99.99), s("D", "C4", 0.1)],
                              [], set(), rules(), None)
        self.assertEqual(got, [("A", "C1", 3), ("B", "C2", 1)])

    def test_money_is_exact_never_a_float_rounding(self):
        # 0.1 + 0.2 as floats is 0.30000000000000004: a spend of 0.3 must give exactly one entry, not none or two
        got = draw.entries_of([s("A", "C1", 0.3)], [], set(), rules(spend_per_entry=0.3), None)
        self.assertEqual(got, [("A", "C1", 1)])
        got = draw.entries_of([s("A", "C1", 300)], [{"return_against": "A", "base_grand_total": -0.01}], set(),
                              rules(), None)
        self.assertEqual(got, [("A", "C1", 2)])

    def test_the_order_is_the_real_time_as_the_shop_sends_it(self):
        # the shop sends a time with no leading zero on the hour, with or without fractions: text order is not time order
        got = draw.entries_of([s("A", "C1", 100, time_="10:00:00"), s("B", "C2", 100, time_="9:05:00"),
                               s("C", "C3", 100, time_="23:00:00"), s("D", "C4", 100, time_="3:00:00.250000"),
                               s("E", "C5", 100, time_="3:00:00")], [], set(), rules(), None)
        self.assertEqual([g[0] for g in got], ["E", "D", "B", "A", "C"])
        self.assertEqual(draw.seconds_of("14:30:12.5"), 52212.5)

    def test_the_total_is_what_the_customer_paid(self):
        # the shop rounds 399.60 to 400 on the receipt: 2 entries at 200, as the customer was told
        sale = dict(s("A", "C1", 399.6), base_rounded_total=400)
        self.assertEqual(draw.entries_of([sale], [], set(), rules(spend_per_entry=200), None), [("A", "C1", 2)])
        self.assertEqual(draw.entries_of([dict(sale, base_rounded_total=0)], [], set(), rules(spend_per_entry=200), None),
                         [("A", "C1", 1)])                    # a shop that does not round: the total
        back = [{"return_against": "A", "base_grand_total": -199.6, "base_rounded_total": -200}]
        self.assertEqual(draw.entries_of([sale], back, set(), rules(spend_per_entry=200), None), [("A", "C1", 1)])

    def test_the_order_is_date_then_time_then_number(self):
        got = draw.entries_of([s("B", "C1", 100, time_="09:00:00"), s("A", "C2", 100, time_="09:00:00"),
                               s("Z", "C3", 100, day="2026-10-01", time_="23:00:00")], [], set(), rules(), None)
        self.assertEqual([g[0] for g in got], ["Z", "A", "B"])

    def test_outside_the_days_or_tills_or_groups_or_walk_in_is_no_entry(self):
        r = rules(tills=[{"pos_profile": "POS-A"}])
        got = draw.entries_of([s("A", "C1", 500, day="2026-09-30"), s("B", "C1", 500, day="2026-11-01"),
                               s("C", "C1", 500, till="POS-B"), s("D", "WALK", 500), s("E", "C2", 500, group="Staff"),
                               s("F", "C3", 500, day="2026-10-31")], [], {"WALK"}, r, {"All"})
        self.assertEqual(got, [("F", "C3", 5)])

    def test_returns_add_up_and_a_sale_returned_whole_gives_none(self):
        back = [{"return_against": "A", "base_grand_total": -150}, {"return_against": "A", "base_grand_total": -100},
                {"return_against": "B", "base_grand_total": -500}]
        got = draw.entries_of([s("A", "C1", 500), s("B", "C2", 500)], back, set(), rules(), None)
        self.assertEqual(got, [("A", "C1", 2)])

    def test_a_total_that_is_not_a_number_is_no_entry(self):
        got = draw.entries_of([s("A", "C1", None), s("B", "C1", "abc"), s("C", "C1", True), s("D", "C1", float("nan"))],
                              [], set(), rules(), None)
        self.assertEqual(got, [])

    def test_the_group_tree_takes_the_groups_below(self):
        tree = [{"name": "All", "lft": 1, "rgt": 8}, {"name": "Members", "lft": 2, "rgt": 5},
                {"name": "Gold", "lft": 3, "rgt": 4}, {"name": "Staff", "lft": 6, "rgt": 7}]
        self.assertEqual(draw.groups_under(tree, ["Members"]), {"Members", "Gold"})
        self.assertEqual(draw.groups_under(tree, ["Gold"]), {"Gold"})
        self.assertEqual(draw.groups_under(tree, ["All"]), {"All", "Members", "Gold", "Staff"})


class Rules(unittest.TestCase):
    def test_a_rule_is_read_or_named_in_a_sentence(self):
        r = rules(most_entries_per_sale=None, winners=None, reserves="")
        self.assertEqual((r.most, r.winners, r.reserves), (0, 1, 0))
        for bad in ({"spend_per_entry": -1}, {"spend_per_entry": "x"}, {"winners": 1.5}, {"reserves": True},
                    {"hours_from_utc": 24}, {"hours_from_utc": -13}, {"hours_from_utc": "4"},
                    {"to_date": "2026-09-01"}, {"company": ""}):
            self.assertIsInstance(draw.rules_of(dict({"company": "PP Co", "from_date": "2026-10-01",
                                                      "to_date": "2026-10-31", "spend_per_entry": 100}, **bad)), str, bad)

    def test_the_shops_day_is_utc_moved_by_its_hours(self):
        t = datetime.datetime(2026, 10, 31, 21, 0, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual(draw.today_at(4, t), datetime.date(2026, 11, 1))
        self.assertEqual(draw.today_at(None, t), datetime.date(2026, 10, 31))
        self.assertEqual(draw.today_at(-6, t), datetime.date(2026, 10, 31))


class AlreadyDrawn(unittest.TestCase):
    def test_a_status_set_back_by_hand_is_still_drawn(self):
        self.assertFalse(draw.already_drawn({"status": "Open", "results": []}))
        for c in ({"status": "Drawn"}, {"status": "Open", "drawn_on": "2026-11-01 06:00 UTC"},
                  {"status": "Open", "draw_fingerprint": "ab"}, {"status": "Open", "drawn_numbers": "4"},
                  {"status": "Open", "results": [{"customer": "C1"}]}):
            self.assertTrue(draw.already_drawn(c), c)


class Draw(unittest.TestCase):
    E = [("S1", "A", 1), ("S2", "B", 3), ("S3", "A", 2), ("S4", "C", 4)]   # A holds 3 of 10 entries, B 3, C 4

    def test_each_entry_has_the_same_chance(self):
        rnd, wins = random.Random(44), {"A": 0, "B": 0, "C": 0}
        for _ in range(20000):
            wins[draw.draw(self.E, 1, rnd.randrange)[0]["customer"]] += 1
        for c, share in (("A", 0.3), ("B", 0.3), ("C", 0.4)):
            self.assertAlmostEqual(wins[c] / 20000, share, delta=0.015, msg=c)

    def test_a_customer_wins_once_and_the_numbers_are_the_whole_lists(self):
        for seed in range(200):
            got = draw.draw(self.E, 3, random.Random(seed).randrange)
            self.assertEqual(sorted(g["customer"] for g in got), ["A", "B", "C"])
            for g in got:          # every drawn number lies inside its sale's own entries, numbered through the list
                start = {"S1": 1, "S2": 2, "S3": 5, "S4": 7}[g["sale"]]
                n = dict((e[0], e[2]) for e in self.E)[g["sale"]]
                self.assertTrue(start <= g["entry_no"] < start + n, g)
                self.assertEqual(g["entries"], {"A": 3, "B": 3, "C": 4}[g["customer"]])

    def test_the_draw_asks_the_random_source_for_the_pool_left(self):
        asked = []
        draw.draw(self.E, 3, lambda n: asked.append(n) or 0)
        self.assertEqual(asked, [10, 7, 4])      # A's 3 leave, then B's 3

    def test_more_places_than_customers_and_no_entries(self):
        self.assertEqual(len(draw.draw(self.E, 9, random.Random(1).randrange)), 3)
        self.assertEqual(draw.draw([], 3, random.Random(1).randrange), [])

    def test_results_rank_winners_then_reserves(self):
        rows = draw.results_of([{"customer": c} for c in "ABC"], 2)
        self.assertEqual([(r["rank"], r["kind"]) for r in rows], [(1, "Winner"), (2, "Winner"), (3, "Reserve")])


class Fingerprint(unittest.TestCase):
    def test_the_same_list_gives_the_same_fingerprint_and_any_change_another(self):
        a = [("S1", "C1", 3), ("S2", "C2", 1)]
        self.assertEqual(draw.fingerprint(a), draw.fingerprint(list(a)))
        for b in ([("S1", "C1", 2), ("S2", "C2", 1)], [("S2", "C2", 1), ("S1", "C1", 3)], a[:1]):
            self.assertNotEqual(draw.fingerprint(a), draw.fingerprint(b))


class Answers(unittest.TestCase):
    def test_every_answer_fits_the_answers_limit(self):
        long = draw.already_answer("2026-11-01 06:00 UTC", "x" * 400)
        self.assertLessEqual(len(long["message"]["body"]), 280)
        self.assertTrue(long["message"]["body"].endswith("…"))

    def test_words_count_one_and_many(self):
        self.assertEqual(draw.count_answer([("S1", "C1", 1)])["message"]["body"], "1 sale by 1 customer: 1 entry so far.")
        self.assertEqual(draw.count_answer([("S1", "C1", 1200)])["message"]["body"], "1 sale by 1 customer: 1,200 entries so far.")
        self.assertEqual(draw.count_answer([])["message"]["level"], "info")


class Press(unittest.TestCase):
    def test_a_press_must_name_one_campaign(self):
        ok = {"point": "desk_action/1", "context": {"v": 1, "user": "u", "records": [{"doctype": draw.CAMPAIGN, "name": "X"}]}}
        self.assertEqual(draw.campaign_of(ok), ("X", "u"))
        for bad in ({"point": "x"}, {"point": "desk_action/1", "context": {"v": 2, "records": []}},
                    {"point": "desk_action/1", "context": {"v": 1, "records": [{"doctype": "Batch", "name": "X"}]}},
                    {"point": "desk_action/1", "context": {"v": 1, "records": [{"doctype": draw.CAMPAIGN, "name": ""}]}}):
            with self.assertRaises(ValueError):
                draw.campaign_of(bad)


if __name__ == "__main__":
    unittest.main()
