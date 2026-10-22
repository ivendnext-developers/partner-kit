"""S36's rules, pure: the boarding pass read (IATA's bar-coded pass, format M), the airport and the day, the item group
tree and each allowance, the shop's settings and the check's shape.

    python3 -m unittest discover -s samples/s36_duty_free/tests -p 'test_*.py'
"""

import datetime
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import dutyfree  # noqa: E402

NOW = datetime.datetime(2026, 10, 22, 12, 0, tzinfo=datetime.timezone.utc).timestamp()   # day 295 of the year
TODAY = datetime.date(2026, 10, 22)


def leg(frm="DXB", to="LHR", carrier="EK", flight="0001", day=295, pnr="ABC123", cond=""):
    """One leg's fixed 37 characters, then its variable part (its size in two hex digits)."""
    return f"{pnr:<7}{frm}{to}{carrier:<3}{flight:<5}{day:03d}Y012A0001 1{len(cond):02X}{cond}"


def bcbp(*legs_, name="DOE/JANE"):
    """A boarding pass's code, as a scanner reads it."""
    legs_ = legs_ or (leg(),)
    return f"M{len(legs_)}{name:<20}E" + "".join(legs_)


PASS = bcbp()
GROUPS = [   # the tree: All > Liquor > Spirits > Whisky; All > Tobacco; All > Food
    {"name": "All Item Groups", "lft": 1, "rgt": 12, "pp_dfa_allowance": 0, "pp_dfa_unit": None},
    {"name": "Liquor", "lft": 2, "rgt": 7, "pp_dfa_allowance": 0, "pp_dfa_unit": None},
    {"name": "Spirits", "lft": 3, "rgt": 6, "pp_dfa_allowance": 4, "pp_dfa_unit": "litres"},
    {"name": "Whisky", "lft": 4, "rgt": 5, "pp_dfa_allowance": 0, "pp_dfa_unit": None},
    {"name": "Tobacco", "lft": 8, "rgt": 9, "pp_dfa_allowance": 400, "pp_dfa_unit": "cigarettes"},
    {"name": "Food", "lft": 10, "rgt": 11, "pp_dfa_allowance": None, "pp_dfa_unit": ""},
]
SETTINGS = {"airports": "DXB, dwc", "direction": "departing", "hours_from_utc": 4, "count_earlier_sales": 1}


def context(lines=None, pass_text=PASS, stage="sale", prefix="PP DFA"):
    lines = [{"line_no": 1, "item_code": "WHISKY-1L", "item_group": "Whisky", "qty_milli": 1000, "uom": "Nos",
              "rate_minor": 5000, "amount_minor": 5000, "discount_minor": 0, "line_attributes": []}] if lines is None else lines
    attrs = [{"name": f"{prefix} Boarding Pass", "value": pass_text}] if pass_text else []
    return {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "sale-1", "store": "Stores - DXB",
            "pos_profile": "Departures", "company": "Shop LLC", "currency": "AED", "lang": "en", "operator": "cashier@shop.example",
            "customer": "Walk In", "customer_group": "Individual", "price_list": "Standard Selling", "coupon_codes": [],
            "sale_attributes": attrs, "lines": lines,
            "totals": {"net_minor": 5000, "tax_minor": 0, "discount_minor": 0, "grand_minor": 5000},
            "offered_tenders": ["Cash"], "pos_opening": "POS-OPE-1", "pos_terminal": "T1"}


def line(code, group, qty=1, uom="Nos"):
    return {"line_no": 1, "item_code": code, "item_group": group, "qty_milli": int(qty * 1000), "uom": uom,
            "rate_minor": 100, "amount_minor": 100, "discount_minor": 0, "line_attributes": []}


class Pass(unittest.TestCase):
    def test_a_one_leg_pass_is_read(self):
        self.assertEqual(dutyfree.legs(PASS), [{"from": "DXB", "to": "LHR", "flight": "EK0001", "day": 295}])

    def test_every_leg_is_read_past_each_legs_variable_part(self):
        text = bcbp(leg("LHR", "DXB", day=294, cond=">5180"), leg("DXB", "BOM", flight="0500", day=295))
        self.assertEqual([(x["from"], x["to"], x["day"]) for x in dutyfree.legs(text)], [("LHR", "DXB", 294), ("DXB", "BOM", 295)])

    def test_a_leg_cut_short_ends_the_reading_and_keeps_the_legs_before_it(self):
        text = bcbp(leg(cond="X" * 60), leg("DXB", "BOM"))[:140]       # the till keeps 140 characters
        self.assertEqual([x["from"] for x in dutyfree.legs(text)], ["DXB"])

    def test_what_is_not_a_boarding_pass_reads_nothing(self):
        for text in ("", "RX-551", "M1DOE/JANE", "S1" + PASS[2:], "M5" + PASS[2:], PASS.replace("295", "ABC"),
                     PASS.replace("295", "400"), PASS.replace("DXB", "D1B"), PASS[:58] + "ZZ"):
            self.assertEqual(dutyfree.legs(text), [], text)

    def test_today_is_the_airports_own_day(self):
        late = datetime.datetime(2026, 10, 22, 21, 30, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual(dutyfree.today_at(4, late), datetime.date(2026, 10, 23))
        self.assertEqual(dutyfree.today_at(0, late), datetime.date(2026, 10, 22))
        self.assertEqual(dutyfree.today_at(-5, NOW - 13 * 3600), datetime.date(2026, 10, 21))


class Judge(unittest.TestCase):
    S = dutyfree.settings_of(SETTINGS)

    def test_a_flight_from_the_shops_airport_today_or_tomorrow_passes(self):
        for day in (295, 296):
            self.assertEqual(dutyfree.pass_problem(bcbp(leg(day=day)), self.S, TODAY), "", day)
        self.assertEqual(dutyfree.pass_problem(bcbp(leg("DWC", "CAI")), self.S, TODAY), "")

    def test_a_flight_from_another_airport_is_refused_naming_both(self):
        out = dutyfree.pass_problem(bcbp(leg("LHR", "DXB")), self.S, TODAY)
        self.assertEqual(out, "This boarding pass is for a flight from LHR. This shop sells to passengers departing DWC, DXB.")

    def test_a_connecting_passenger_passes_on_the_leg_that_leaves_here(self):
        text = bcbp(leg("LHR", "DXB", day=294), leg("DXB", "BOM", day=295))
        self.assertEqual(dutyfree.pass_problem(text, self.S, TODAY), "")

    def test_another_days_flight_is_refused(self):
        for day in (294, 297, 1):
            self.assertEqual(dutyfree.pass_problem(bcbp(leg(day=day)), self.S, TODAY), dutyfree.OTHER_DAY, day)

    def test_the_day_crosses_the_new_year(self):
        self.assertEqual(dutyfree.pass_problem(bcbp(leg(day=1)), self.S, datetime.date(2026, 12, 31)), "")
        arriving = dutyfree.settings_of(dict(SETTINGS, direction="arriving"))
        self.assertEqual(dutyfree.pass_problem(bcbp(leg("LHR", "DXB", day=365)), arriving, datetime.date(2027, 1, 1)), "")

    def test_an_arrivals_shop_takes_a_flight_landing_here_today_or_yesterday(self):
        arriving = dutyfree.settings_of(dict(SETTINGS, direction="arriving"))
        for day in (294, 295):
            self.assertEqual(dutyfree.pass_problem(bcbp(leg("LHR", "DXB", day=day)), arriving, TODAY), "", day)
        self.assertEqual(dutyfree.pass_problem(bcbp(leg("LHR", "DXB", day=296)), arriving, TODAY), dutyfree.OTHER_DAY)
        self.assertEqual(dutyfree.pass_problem(bcbp(leg("DXB", "LHR")), arriving, TODAY),
                         "This boarding pass is for a flight to LHR. This shop sells to passengers arriving at DWC, DXB.")

    def test_no_airports_set_takes_any_airport(self):
        s = dutyfree.settings_of(dict(SETTINGS, airports=""))
        self.assertEqual(dutyfree.pass_problem(bcbp(leg("LHR", "JFK")), s, TODAY), "")

    def test_an_unreadable_pass_is_refused(self):
        self.assertEqual(dutyfree.pass_problem("RX-551", self.S, TODAY), dutyfree.UNREADABLE)


class Allowance(unittest.TestCase):
    G = dutyfree.groups_of(GROUPS, "PP DFA")

    def test_a_groups_allowance_covers_the_groups_below_it(self):
        self.assertEqual(dutyfree.limited_groups("Whisky", self.G), ["Spirits"])
        self.assertEqual(dutyfree.limited_groups("Spirits", self.G), ["Spirits"])
        self.assertEqual(dutyfree.limited_groups("Liquor", self.G), [])
        self.assertEqual(dutyfree.limited_groups("Food", self.G), [])
        self.assertEqual(dutyfree.limited_groups("Not A Group", self.G), [])

    def test_at_the_allowance_passes_and_past_it_is_refused_in_its_own_unit(self):
        self.assertEqual(dutyfree.over_allowance([("Whisky", 3.0), ("Spirits", 1.0)], self.G, {"Spirits"}), "")
        self.assertEqual(dutyfree.over_allowance([("Whisky", 3.0), ("Spirits", 1.5)], self.G, {"Spirits"}),
                         "Spirits: 4.5 litres on this boarding pass; the allowance is 4. Take some off the sale.")

    def test_a_return_takes_its_amount_back(self):
        self.assertEqual(dutyfree.over_allowance([("Whisky", 4.0), ("Whisky", -1.0), ("Whisky", 1.0)], self.G, {"Spirits"}), "")

    def test_only_the_groups_this_sale_touches_are_judged(self):
        rows = [("Tobacco", 600.0), ("Whisky", 1.0)]
        self.assertEqual(dutyfree.over_allowance(rows, self.G, {"Spirits"}), "")
        self.assertIn("Tobacco: 600 cigarettes", dutyfree.over_allowance(rows, self.G, {"Spirits", "Tobacco"}))

    def test_a_unit_left_blank_reads_as_a_number_alone(self):
        g = dutyfree.groups_of([dict(GROUPS[4], pp_dfa_unit="")], "PP DFA")
        self.assertEqual(dutyfree.over_allowance([("Tobacco", 401.0)], g, {"Tobacco"}),
                         "Tobacco: 401 on this boarding pass; the allowance is 400. Take some off the sale.")

    def test_rounding_never_refuses_an_amount_at_the_allowance(self):
        rows = [("Whisky", 0.1)] * 40
        self.assertEqual(dutyfree.over_allowance(rows, self.G, {"Spirits"}), "")

    def test_the_prefix_names_the_fields(self):
        g = dutyfree.groups_of([{"name": "X", "lft": 1, "rgt": 2, "ivendnext_dfa_allowance": 2, "ivendnext_dfa_unit": "l"}],
                               "IVENDNEXT DFA")
        self.assertEqual(g["X"], (1, 2, 2.0, "l"))

    def test_groups_that_are_not_records_are_refused(self):
        for bad in (None, {}, [{"name": "X"}], [{"name": "X", "lft": "1", "rgt": 2}]):
            with self.assertRaises(ValueError):
                dutyfree.groups_of(bad, "PP DFA")


class Settings(unittest.TestCase):
    def test_the_record_read(self):
        s = dutyfree.settings_of(SETTINGS)
        self.assertEqual(s, {"airports": ["DWC", "DXB"], "arriving": False, "hours": 4.0, "earlier": True})

    def test_no_record_is_any_airport_departures_utc_and_earlier_sales_counted(self):
        self.assertEqual(dutyfree.settings_of(None), {"airports": [], "arriving": False, "hours": 0.0, "earlier": True})

    def test_odd_values_read_safely(self):
        s = dutyfree.settings_of({"airports": "DXB1, D, dubai, JED", "hours_from_utc": 30, "count_earlier_sales": 0})
        self.assertEqual((s["airports"], s["hours"], s["earlier"]), (["JED"], 0.0, False))


class Context(unittest.TestCase):
    def test_a_good_call_reads(self):
        self.assertEqual(dutyfree.check_context({"point": "check/1", "context": context()})["stage"], "sale")

    def test_a_bad_shape_is_refused_before_any_decision(self):
        bad = [None, {"point": "check/2", "context": context()}, {"point": "check/1", "context": dict(context(), v=2)},
               {"point": "check/1", "context": dict(context(), lines=[{"item_code": "X"}])},
               {"point": "check/1", "context": dict(context(), lines=[dict(line("X", "G"), qty_milli="1000")])},
               {"point": "check/1", "context": dict(context(), sale_attributes=[{"name": "PP DFA Boarding Pass"}])},
               {"point": "check/1", "context": dict(context(), sale_attributes=None)}]
        for body in bad:
            with self.assertRaises(ValueError):
                dutyfree.check_context(body)

    def test_the_pass_is_the_prefixs_own_sale_detail(self):
        self.assertEqual(dutyfree.pass_of(context(), "PP DFA"), PASS)
        self.assertEqual(dutyfree.pass_of(context(prefix="OTHER"), "PP DFA"), "")
        self.assertEqual(dutyfree.pass_of(context(pass_text=""), "PP DFA"), "")

    def test_a_refund_sells_nothing_and_an_exchange_sells(self):
        self.assertFalse(dutyfree.sells(context([line("X", "Whisky", -1)], stage="return")))
        self.assertTrue(dutyfree.sells(context([line("X", "Whisky", -1), line("Y", "Whisky", 1)], stage="return")))

    def test_every_sentence_is_plain_and_at_most_140(self):
        g = dutyfree.groups_of([{"name": "<b>" + "S" * 200, "lft": 1, "rgt": 2, "pp_dfa_allowance": 1, "pp_dfa_unit": "u" * 90}],
                               "PP DFA")
        out = dutyfree.over_allowance([("<b>" + "S" * 200, 9.0)], g, set(g))
        s = dutyfree.settings_of({"airports": " ".join(a + b + "X" for a in "ABCDEFGH" for b in "ABCDEFGH")})
        for text in (out, dutyfree.pass_problem(bcbp(leg("LHR")), s, TODAY), dutyfree.NO_PASS, dutyfree.UNREADABLE,
                     dutyfree.OTHER_DAY):
            self.assertTrue(0 < len(text) <= 140 and "<" not in text and ">" not in text, text)


if __name__ == "__main__":
    unittest.main()
