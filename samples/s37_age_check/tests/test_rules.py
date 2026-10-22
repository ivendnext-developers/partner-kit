"""S37's rules, pure: each item's age (its own, else the nearest group with one), the date of birth shown at the scan, the
check recorded on the sale and the refusal at Pay, the remembered asks, the shop's settings and the shapes.

    python3 -m unittest discover -s samples/s37_age_check/tests -p 'test_*.py'
"""

import datetime
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import agecheck  # noqa: E402

NOW = datetime.datetime(2026, 10, 22, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
TODAY = datetime.date(2026, 10, 22)
GROUPS = [   # the tree: All > Drinks > Alcohol > Spirits; Alcohol > Beer (its own 16); All > Tobacco > Vapes (21); All > Food
    {"name": "All Item Groups", "lft": 1, "rgt": 18, "pp_age_min_age": 0},
    {"name": "Drinks", "lft": 2, "rgt": 9, "pp_age_min_age": None},
    {"name": "Alcohol", "lft": 3, "rgt": 8, "pp_age_min_age": 18},
    {"name": "Spirits", "lft": 4, "rgt": 5, "pp_age_min_age": 0},
    {"name": "Beer", "lft": 6, "rgt": 7, "pp_age_min_age": 16},
    {"name": "Tobacco", "lft": 10, "rgt": 13, "pp_age_min_age": 18},
    {"name": "Vapes", "lft": 11, "rgt": 12, "pp_age_min_age": 21},
    {"name": "Food", "lft": 14, "rgt": 17, "pp_age_min_age": 0},
]
ITEMS = [{"name": "WHISKY", "pp_age_min_age": 0}, {"name": "KNIFE", "pp_age_min_age": 18},
         {"name": "BREAD", "pp_age_min_age": None}, {"name": "VAPE", "pp_age_min_age": 0}, {"name": "LAGER", "pp_age_min_age": 0},
         {"name": "COLA", "pp_age_min_age": 0},
         {"name": "POD", "pp_age_min_age": 21, "variant_of": None},             # a template in a group of no age
         {"name": "POD-MINT", "pp_age_min_age": 0, "variant_of": "POD"},        # its variant: the field was not copied
         {"name": "POD-MILD", "pp_age_min_age": 18, "variant_of": "POD"}]       # a variant with its own age
SETTINGS = {"hours_from_utc": 4, "look_under": 25}
G, I = agecheck.groups_of(GROUPS, "PP AGE"), agecheck.items_of(ITEMS, "PP AGE")


def line(code, group, qty=1, n=1):
    return {"line_no": n, "item_code": code, "item_group": group, "qty_milli": int(qty * 1000), "uom": "Nos",
            "rate_minor": 100, "amount_minor": 100, "discount_minor": 0, "line_attributes": []}


def context(lines=None, checked=None, stage="sale", prefix="PP AGE"):
    lines = [line("WHISKY", "Spirits")] if lines is None else lines
    attrs = [{"name": f"{prefix} ID Checked", "value": checked}] if checked is not None else []
    return {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "sale-1", "store": "Stores - DXB",
            "pos_profile": "Main", "company": "Shop LLC", "currency": "AED", "lang": "en", "operator": "cashier@shop.example",
            "customer": "Walk In", "customer_group": "Individual", "price_list": "Standard Selling", "coupon_codes": [],
            "sale_attributes": attrs, "lines": lines,
            "totals": {"net_minor": 100, "tax_minor": 0, "discount_minor": 0, "grand_minor": 100},
            "offered_tenders": ["Cash"], "pos_opening": "POS-OPE-1", "pos_terminal": "T1"}


def scan(code="WHISKY", group="Spirits", sale_ref="sale-1"):
    return {"v": 1, "point": "capture", "event": "scan", "sale_ref": sale_ref, "store": "Stores - DXB", "pos_profile": "Main",
            "operator": "cashier@shop.example", "customer": None, "lang": "en",
            "line": {"item_code": code, "item_group": group, "qty_milli": 1000, "uom": "Nos", "batch_no": "", "serial_no": "",
                     "scanned_code": "5000000000001"}}


def ages(ctx):
    return [agecheck.age_of(x["item_code"], x["item_group"], I, G) for x in ctx["lines"]]


class Ages(unittest.TestCase):
    def test_a_groups_age_covers_the_groups_below_it(self):
        self.assertEqual(agecheck.age_of("WHISKY", "Spirits", I, G), 18)

    def test_the_nearest_group_with_an_age_wins(self):
        self.assertEqual(agecheck.age_of("LAGER", "Beer", I, G), 16)      # Beer 16 inside Alcohol 18
        self.assertEqual(agecheck.age_of("VAPE", "Vapes", I, G), 21)      # Vapes 21 inside Tobacco 18

    def test_an_items_own_age_wins_over_its_group(self):
        self.assertEqual(agecheck.age_of("KNIFE", "Food", I, G), 18)

    def test_a_variant_with_no_age_of_its_own_takes_its_templates(self):
        self.assertEqual(agecheck.age_of("POD-MINT", "Food", I, G), 21)
        self.assertEqual(agecheck.age_of("POD-MILD", "Food", I, G), 18)
        self.assertEqual(I["POD-MINT"], (0, "POD"))

    def test_no_age_anywhere_is_zero(self):
        self.assertEqual(agecheck.age_of("BREAD", "Food", I, G), 0)
        self.assertEqual(agecheck.age_of("COLA", "Unknown group", I, G), 0)

    def test_an_age_that_is_not_a_whole_age_is_no_age(self):
        got = agecheck.groups_of([{"name": "X", "lft": 1, "rgt": 2, "pp_age_min_age": v} for v in (0,)], "PP AGE")
        self.assertEqual(got["X"][2], 0)
        for v in (-1, 0.5, 121, "18", True, None):
            self.assertEqual(agecheck._age(v), 0, v)
        self.assertEqual(agecheck._age(18.0), 18)

    def test_groups_that_are_not_records_are_refused(self):
        for bad in (None, {"data": []}, [{"name": "X", "lft": "1", "rgt": 2}]):
            with self.assertRaises(ValueError):
                agecheck.groups_of(bad, "PP AGE")
        with self.assertRaises(ValueError):
            agecheck.items_of([{"item": "X"}], "PP AGE")

    def test_the_prefix_names_the_field(self):
        got = agecheck.groups_of([{"name": "X", "lft": 1, "rgt": 2, "ivendnext_age_min_age": 21, "pp_age_min_age": 18}],
                                 "IVENDNEXT AGE")
        self.assertEqual(got["X"][2], 21)


class Scan(unittest.TestCase):
    def test_a_restricted_item_shows_the_date_and_records_the_check(self):
        s = agecheck.settings_of(SETTINGS)
        out = agecheck.on_scan(scan(), 18, s, TODAY, "PP AGE")
        self.assertEqual(out, {"verdict": "notice",
                               "message": "WHISKY: customers 18 or over. Born on or before 22 Oct 2008. Ask for ID if they look under 25.",
                               "sale_attributes": [{"sale_attribute": "PP AGE ID Checked", "attribute_value": "18 or over"}]})

    def test_see_their_id_when_the_shop_has_no_policy_or_it_is_not_above_the_age(self):
        for look in (0, None, 21):
            out = agecheck.on_scan(scan("VAPE", "Vapes"), 21, agecheck.settings_of({"look_under": look}), TODAY, "PP AGE")
            self.assertTrue(out["message"].endswith("Born on or before 22 Oct 2005. See their ID."), out)

    def test_no_age_is_allow_with_nothing_shown(self):
        self.assertEqual(agecheck.on_scan(scan("BREAD", "Food"), 0, agecheck.settings_of(SETTINGS), TODAY, "PP AGE"),
                         {"verdict": "allow"})

    def test_born_by_is_the_same_day_that_many_years_ago_and_29_february_is_the_28th(self):
        self.assertEqual(agecheck.born_by(datetime.date(2026, 10, 22), 18), datetime.date(2008, 10, 22))
        self.assertEqual(agecheck.born_by(datetime.date(2028, 2, 29), 21), datetime.date(2007, 2, 28))

    def test_today_is_the_shops_own_day(self):
        late = NOW + 9.5 * 3600                  # 21:30 UTC on the 22nd: already the 23rd in Dubai, still the 22nd in Mexico
        self.assertEqual(agecheck.today_at(4, late), datetime.date(2026, 10, 23))
        self.assertEqual(agecheck.today_at(-6, late), datetime.date(2026, 10, 22))

    def test_every_sentence_is_plain_and_at_most_140(self):
        out = agecheck.on_scan(scan("W<b>" * 30), 120, agecheck.settings_of({"look_under": 120}), TODAY, "PP AGE")
        self.assertLessEqual(len(out["message"]), 140)
        self.assertNotIn("<", out["message"])


class Check(unittest.TestCase):
    def test_a_restricted_line_with_no_check_is_refused_naming_it_and_the_age(self):
        ctx = context([line("BREAD", "Food", n=1), line("WHISKY", "Spirits", n=2)])
        self.assertEqual(agecheck.on_check(ctx, ages(ctx), agecheck.checked_age(ctx, "PP AGE")), {"verdict": "refuse", "reason":
                         "Line 2: WHISKY is for customers 18 or over. See their ID, then enter 18 in Sale details, or take it off."})

    def test_a_recorded_check_at_the_age_or_above_allows(self):
        for checked in ("18 or over", "18", " 21 ", "25 or over"):
            ctx = context(checked=checked)
            self.assertEqual(agecheck.on_check(ctx, ages(ctx), agecheck.checked_age(ctx, "PP AGE")), {"verdict": "allow"}, checked)

    def test_a_lower_check_is_refused_naming_the_highest_age_needed(self):
        ctx = context([line("LAGER", "Beer", n=1), line("WHISKY", "Spirits", n=2), line("VAPE", "Vapes", n=3)], checked="16")
        self.assertEqual(agecheck.on_check(ctx, ages(ctx), agecheck.checked_age(ctx, "PP AGE"))["reason"],
                         "Line 3: VAPE is for customers 21 or over; the sale's ID check says 16. See their ID, then enter 21 in Sale details.")

    def test_only_a_whole_age_alone_is_a_check(self):
        for checked, age in (("18 or over", 18), ("18", 18), (" 21+ ", 21), ("21 OR OVER", 21), ("18/03/2010", 0),
                             ("DOB 25.11.2009", 0), ("1999", 0), ("2010-03-18", 0), ("over 18", 0), ("121", 0)):
            self.assertEqual(agecheck.checked_age(context(checked=checked), "PP AGE"), age, checked)

    def test_a_check_that_is_not_a_number_counts_as_none(self):
        for checked in ("yes", "", "ok seen"):
            ctx = context(checked=checked)
            self.assertEqual(agecheck.checked_age(ctx, "PP AGE"), 0, checked)
            self.assertEqual(agecheck.on_check(ctx, ages(ctx), 0)["verdict"], "refuse")

    def test_another_apps_sale_detail_is_not_this_apps_check(self):
        ctx = context(checked="21", prefix="OTHER")
        self.assertEqual(agecheck.checked_age(ctx, "PP AGE"), 0)

    def test_a_sale_of_nothing_restricted_is_allowed(self):
        ctx = context([line("BREAD", "Food")])
        self.assertEqual(agecheck.on_check(ctx, ages(ctx), 0), {"verdict": "allow"})

    def test_a_return_is_judged_only_for_what_it_sells(self):
        ctx = context([line("WHISKY", "Spirits", -1)], stage="return")
        self.assertFalse(agecheck.sells(ctx))
        self.assertEqual(agecheck.on_check(ctx, ages(ctx), 0), {"verdict": "allow"})
        ctx = context([line("WHISKY", "Spirits", -1, n=1), line("VAPE", "Vapes", 1, n=2)], stage="return")
        self.assertIn("Line 2: VAPE", agecheck.on_check(ctx, ages(ctx), 0)["reason"])

    def test_a_line_with_no_number_is_named_by_its_place(self):
        ctx = context([dict(line("BREAD", "Food"), line_no=None), dict(line("WHISKY", "Spirits"), line_no=None)])
        self.assertTrue(agecheck.on_check(ctx, ages(ctx), 0)["reason"].startswith("Line 2: WHISKY"))

    def test_every_refusal_is_plain_and_at_most_140(self):
        long = "W" * 200
        for checked in (0, 18):
            ctx = context([line(long, "Vapes", n=123)])
            reason = agecheck.on_check(ctx, [21], checked)["reason"]
            self.assertLessEqual(len(reason), 140)
            self.assertTrue(reason.endswith("in Sale details.") or reason.endswith("or take it off."), reason)   # never cut


class Asked(unittest.TestCase):
    def setUp(self):
        self.t = [1000.0]
        self.a = agecheck.Asked(lambda: self.t[0])

    def test_a_sale_asked_about_at_an_age_is_covered_for_that_age_and_below(self):
        self.a.remember("shop", "sale-1", 21)
        self.assertTrue(self.a.covered("shop", "sale-1", 18))
        self.assertTrue(self.a.covered("shop", "sale-1", 21))
        self.assertFalse(self.a.covered("shop", "sale-1", 25))
        self.a.remember("shop", "sale-1", 18)                 # a lower ask never lowers what was asked
        self.assertTrue(self.a.covered("shop", "sale-1", 21))

    def test_another_sale_or_shop_is_not_covered(self):
        self.a.remember("shop", "sale-1", 18)
        self.assertFalse(self.a.covered("shop", "sale-2", 18))
        self.assertFalse(self.a.covered("other", "sale-1", 18))

    def test_a_sale_with_no_reference_is_never_remembered(self):
        self.a.remember("shop", "", 18)
        self.assertFalse(self.a.covered("shop", "", 18))
        self.assertEqual(self.a.seen, {})

    def test_it_is_forgotten_after_four_hours_and_an_old_age_does_not_carry_over(self):
        self.a.remember("shop", "sale-1", 21)
        self.t[0] += agecheck.ASKED_TTL + 1
        self.assertFalse(self.a.covered("shop", "sale-1", 18))
        self.a.remember("shop", "sale-1", 18)
        self.assertFalse(self.a.covered("shop", "sale-1", 21))

    def test_the_oldest_go_first_past_the_cap(self):
        n = agecheck.ASKED_MAX
        for i in range(n + 2):
            self.a.remember("shop", f"s{i}", 18)
        self.assertEqual(len(self.a.seen), n)
        self.assertFalse(self.a.covered("shop", "s0", 18))
        self.assertTrue(self.a.covered("shop", f"s{n + 1}", 18))


class Settings(unittest.TestCase):
    def test_no_record_is_utc_and_see_their_id(self):
        self.assertEqual(agecheck.settings_of(None), {"hours": 0.0, "look_under": 0})

    def test_hours_past_14_read_0(self):
        self.assertEqual(agecheck.settings_of({"hours_from_utc": 15})["hours"], 0.0)
        self.assertEqual(agecheck.settings_of({"hours_from_utc": -5.5})["hours"], -5.5)


class Context(unittest.TestCase):
    def test_a_bad_shape_is_refused_before_any_decision(self):
        good = {"point": "check/1", "context": context()}
        self.assertEqual(agecheck.check_context(good)["stage"], "sale")
        for bad in ({"point": "capture/1", "context": context()}, {"point": "check/1", "context": dict(context(), v=2)},
                    {"point": "check/1", "context": dict(context(), lines=[{"item_code": "X", "item_group": "Y"}])},
                    {"point": "check/1", "context": dict(context(), sale_attributes=[{"name": "X"}])}):
            with self.assertRaises(ValueError):
                agecheck.check_context(bad)

    def test_a_scan_is_read_only_for_the_scan_event(self):
        self.assertEqual(agecheck.scan_context({"point": "capture/1", "context": scan()})["line"]["item_code"], "WHISKY")
        for bad in ({"point": "capture/1", "context": dict(scan(), event="qty_change")},
                    {"point": "check/1", "context": scan()},
                    {"point": "capture/1", "context": dict(scan(), line={"item_code": ""})},
                    {"point": "capture/1", "context": dict(scan(), sale_ref=7)}):
            with self.assertRaises(ValueError):
                agecheck.scan_context(bad)


if __name__ == "__main__":
    unittest.main()
