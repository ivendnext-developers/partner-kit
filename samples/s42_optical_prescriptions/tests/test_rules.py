"""S42's rules, pure: each item's mark (its own, else its template's, else the nearest group with one), the customer's
prescriptions in date at the shop's own day, the refusal at Pay, the shop's settings and the shapes.

    python3 -m unittest discover -s samples/s42_optical_prescriptions/tests -p 'test_*.py'
"""

import datetime
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import optical  # noqa: E402

NOW = datetime.datetime(2026, 10, 23, 12, 0, tzinfo=datetime.timezone.utc).timestamp()
TODAY = datetime.date(2026, 10, 23)
GROUPS = [   # All > Eyewear > Lenses > Spectacle lenses (Spectacles) > Plano lenses (Not needed);
             # Lenses > Contact lenses (Contact lenses) > Toric contacts (none of its own); All > Frames; All > Solutions
    {"name": "All Item Groups", "lft": 1, "rgt": 18, "pp_opt_needs": ""},
    {"name": "Eyewear", "lft": 2, "rgt": 13, "pp_opt_needs": None},
    {"name": "Lenses", "lft": 3, "rgt": 12, "pp_opt_needs": ""},
    {"name": "Spectacle lenses", "lft": 4, "rgt": 7, "pp_opt_needs": "Spectacles"},
    {"name": "Plano lenses", "lft": 5, "rgt": 6, "pp_opt_needs": "Not needed"},
    {"name": "Contact lenses", "lft": 8, "rgt": 11, "pp_opt_needs": "Contact lenses"},
    {"name": "Toric contacts", "lft": 9, "rgt": 10, "pp_opt_needs": ""},
    {"name": "Frames", "lft": 14, "rgt": 15, "pp_opt_needs": ""},
    {"name": "Solutions", "lft": 16, "rgt": 17, "pp_opt_needs": "Something else"},
]
ITEMS = [{"name": "SV-LENS", "pp_opt_needs": ""}, {"name": "PLANO", "pp_opt_needs": None},
         {"name": "ACUVUE-30", "pp_opt_needs": ""}, {"name": "FRAME-1", "pp_opt_needs": ""},
         {"name": "SUN-RX", "pp_opt_needs": "Spectacles"},                   # its own mark, in a group of none
         {"name": "DEMO-CL", "pp_opt_needs": "Not needed"},                  # its own Not needed, in Contact lenses
         {"name": "TORIC", "pp_opt_needs": "Contact lenses", "variant_of": None},       # a template in Frames
         {"name": "TORIC-2", "pp_opt_needs": "", "variant_of": "TORIC"}]     # its variant: the field was not copied
SETTINGS = {"hours_from_utc": 4}
G, I = optical.groups_of(GROUPS, "PP OPT"), optical.items_of(ITEMS, "PP OPT")
RX_SPECS = {"kind": "Spectacles", "test_date": "2025-11-01", "valid_until": "2027-11-01"}
RX_CL_OLD = {"kind": "Contact lenses", "test_date": "2025-01-10", "valid_until": "2026-01-10"}
RX_CL = {"kind": "Contact lenses", "test_date": "2026-10-01", "valid_until": "2027-10-01"}


def line(code, group, qty=1, n=1):
    return {"line_no": n, "item_code": code, "item_group": group, "qty_milli": int(qty * 1000), "uom": "Nos",
            "rate_minor": 100, "amount_minor": 100, "discount_minor": 0, "line_attributes": []}


def context(lines=None, customer="Ana Lopez", stage="sale"):
    lines = [line("SV-LENS", "Spectacle lenses")] if lines is None else lines
    return {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "sale-1", "store": "Stores - DXB",
            "pos_profile": "Main", "company": "Shop LLC", "currency": "AED", "lang": "en", "operator": "cashier@shop.example",
            "customer": customer, "customer_group": "Individual", "price_list": "Standard Selling", "coupon_codes": [],
            "sale_attributes": [], "lines": lines,
            "totals": {"net_minor": 100, "tax_minor": 0, "discount_minor": 0, "grand_minor": 100},
            "offered_tenders": ["Cash"], "pos_opening": "POS-OPE-1", "pos_terminal": "T1"}


def needs(ctx):
    return [optical.need_of(x["item_code"], x["item_group"], I, G) for x in ctx["lines"]]


def rxs(*records):
    return optical.prescriptions_of(list(records))


class Marks(unittest.TestCase):
    def test_a_groups_mark_covers_the_groups_below_it(self):
        self.assertEqual(optical.need_of("SV-LENS", "Spectacle lenses", I, G), "Spectacles")
        self.assertEqual(optical.need_of("ACUVUE-30", "Contact lenses", I, G), "Contact lenses")
        self.assertEqual(optical.need_of("ACUVUE-30", "Toric contacts", I, G), "Contact lenses")    # a group below

    def test_not_needed_below_a_marked_group_frees_it(self):
        self.assertEqual(optical.need_of("PLANO", "Plano lenses", I, G), "")

    def test_an_items_own_mark_wins_over_its_group(self):
        self.assertEqual(optical.need_of("SUN-RX", "Frames", I, G), "Spectacles")
        self.assertEqual(optical.need_of("DEMO-CL", "Contact lenses", I, G), "")

    def test_a_variant_with_no_mark_of_its_own_takes_its_templates(self):
        self.assertEqual(optical.need_of("TORIC-2", "Frames", I, G), "Contact lenses")
        self.assertEqual(I["TORIC-2"], ("", "TORIC"))

    def test_an_unmarked_item_or_an_unknown_group_needs_nothing(self):
        self.assertEqual(optical.need_of("FRAME-1", "Frames", I, G), "")
        self.assertEqual(optical.need_of("FRAME-1", "No Such Group", I, G), "")

    def test_a_value_that_is_not_one_of_the_marks_is_none(self):
        self.assertEqual(optical.need_of("X", "Solutions", I, G), "")
        self.assertEqual(G["Solutions"][2], "")


class Prescriptions(unittest.TestCase):
    def test_in_date_is_its_kind_tested_on_or_before_today_and_valid_on_or_after_it(self):
        (rx,) = rxs(RX_SPECS)
        self.assertTrue(optical.in_date(rx, "Spectacles", TODAY))
        self.assertFalse(optical.in_date(rx, "Contact lenses", TODAY))
        self.assertTrue(optical.in_date(rx, "Spectacles", datetime.date(2027, 11, 1)))      # its last day
        self.assertFalse(optical.in_date(rx, "Spectacles", datetime.date(2027, 11, 2)))
        self.assertFalse(optical.in_date(rx, "Spectacles", datetime.date(2025, 10, 31)))    # before its test

    def test_a_record_without_its_kind_and_dates_is_unreadable(self):
        for bad in ([{"name": "OPT-RX-00001"}], [{"kind": "Spectacles", "valid_until": "2027-01-01"}], None, {"data": []}):
            with self.assertRaises(ValueError):
                optical.prescriptions_of(bad)

    def test_an_unreadable_date_or_kind_counts_as_none(self):
        got = rxs({"kind": "Spectacles", "test_date": "soon", "valid_until": "2027-01-01"},
                  {"kind": "Glasses", "test_date": "2026-01-01", "valid_until": "2027-01-01"})
        self.assertEqual(got, [("Spectacles", None, datetime.date(2027, 1, 1))])
        self.assertFalse(optical.in_date(got[0], "Spectacles", TODAY))

    def test_today_is_the_shops_own_day(self):
        late = datetime.datetime(2026, 10, 23, 21, 0, tzinfo=datetime.timezone.utc).timestamp()
        self.assertEqual(optical.today_at(4, late), datetime.date(2026, 10, 24))
        self.assertEqual(optical.today_at(0, late), datetime.date(2026, 10, 23))
        self.assertEqual(optical.today_at(-6, NOW - 8 * 3600), datetime.date(2026, 10, 22))

    def test_settings_hours_are_a_number_within_14(self):
        self.assertEqual(optical.settings_of(SETTINGS), {"hours": 4.0})
        for bad in (None, {}, {"hours_from_utc": 20}, {"hours_from_utc": "4"}, {"hours_from_utc": True}):
            self.assertEqual(optical.settings_of(bad), {"hours": 0.0}, bad)


class Check(unittest.TestCase):
    def test_a_lens_line_with_no_prescription_is_refused_naming_it(self):
        out = optical.on_check(context([line("FRAME-1", "Frames", n=1), line("SV-LENS", "Spectacle lenses", n=2)]),
                               ["", "Spectacles"], [], TODAY)
        self.assertEqual(out, {"verdict": "refuse", "reason": "Line 2: SV-LENS needs a spectacle prescription for this "
                               "customer. Add the customer, or enter it in Desk, then Pay again."})

    def test_a_prescription_of_the_kind_in_date_allows(self):
        ctx = context([line("SV-LENS", "Spectacle lenses"), line("ACUVUE-30", "Contact lenses", n=2)])
        self.assertEqual(optical.on_check(ctx, needs(ctx), rxs(RX_SPECS, RX_CL), TODAY), {"verdict": "allow"})

    def test_a_prescription_of_the_other_kind_does_not(self):
        ctx = context([line("ACUVUE-30", "Contact lenses")])
        out = optical.on_check(ctx, needs(ctx), rxs(RX_SPECS), TODAY)
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("needs a contact lens prescription", out["reason"])

    def test_an_expired_one_names_the_day_it_ran_out(self):
        ctx = context([line("ACUVUE-30", "Contact lenses")])
        out = optical.on_check(ctx, needs(ctx), rxs(RX_CL_OLD), TODAY)
        self.assertEqual(out["reason"], "Line 1: ACUVUE-30: the customer's contact lens prescription ran out on 10 Jan "
                         "2026. Enter the new one in Desk, then Pay again.")

    def test_the_latest_ended_one_is_named(self):
        older = dict(RX_CL_OLD, valid_until="2025-06-01")
        ctx = context([line("ACUVUE-30", "Contact lenses")])
        self.assertIn("ran out on 10 Jan 2026", optical.on_check(ctx, needs(ctx), rxs(older, RX_CL_OLD), TODAY)["reason"])

    def test_a_prescription_dated_after_today_is_not_in_date(self):
        future = dict(RX_CL, test_date="2026-11-01")
        ctx = context([line("ACUVUE-30", "Contact lenses")])
        self.assertIn("needs a contact lens", optical.on_check(ctx, needs(ctx), rxs(future), TODAY)["reason"])

    def test_nothing_needing_one_is_allowed(self):
        ctx = context([line("FRAME-1", "Frames"), line("PLANO", "Plano lenses", n=2)])
        self.assertEqual(optical.on_check(ctx, needs(ctx), [], TODAY), {"verdict": "allow"})

    def test_a_return_is_judged_only_for_what_it_sells(self):
        ctx = context([line("SV-LENS", "Spectacle lenses", -1), line("FRAME-1", "Frames", n=2)], stage="return")
        self.assertEqual(optical.on_check(ctx, needs(ctx), [], TODAY), {"verdict": "allow"})
        ctx = context([line("FRAME-1", "Frames", -1), line("SV-LENS", "Spectacle lenses", n=2)], stage="return")
        self.assertEqual(optical.on_check(ctx, needs(ctx), [], TODAY)["verdict"], "refuse")

    def test_the_first_line_short_is_named(self):
        ctx = context([line("FRAME-1", "Frames", n=1), line("ACUVUE-30", "Contact lenses", n=2),
                       line("SV-LENS", "Spectacle lenses", n=3)])
        self.assertTrue(optical.on_check(ctx, needs(ctx), [], TODAY)["reason"].startswith("Line 2: ACUVUE-30"))

    def test_every_refusal_is_plain_and_at_most_140(self):
        long = "<b>" + "W" * 200
        for rx in ([], rxs(RX_CL_OLD)):
            for n in (1, 499):
                out = optical.on_check(context([line(long, "Contact lenses", n=n)]), ["Contact lenses"], rx, TODAY)
                self.assertLessEqual(len(out["reason"]), 140)
                self.assertNotIn("<", out["reason"])
                self.assertTrue(out["reason"].endswith("Pay again."), out["reason"])     # the whole sentence fits


class Context(unittest.TestCase):
    def test_a_bad_shape_is_refused_before_any_decision(self):
        for body in (None, {"point": "capture/1", "context": context()}, {"point": "check/1", "context": {}},
                     {"point": "check/1", "context": dict(context(), lines=[{"item_code": "X"}])},
                     {"point": "check/1", "context": dict(context(), lines=[dict(line("X", "Y"), qty_milli="1")])},
                     {"point": "check/1", "context": dict(context(), customer=None)},
                     {"point": "check/1", "context": dict(context(), stage="quote")}):
            with self.assertRaises(ValueError):
                optical.check_context(body)

    def test_a_good_call_is_read(self):
        self.assertEqual(optical.check_context({"point": "check/1", "context": context()})["customer"], "Ana Lopez")

    def test_a_refund_sells_nothing(self):
        self.assertFalse(optical.sells(context([line("SV-LENS", "Spectacle lenses", -1)], stage="return")))
        self.assertTrue(optical.sells(context()))

    def test_groups_and_items_that_are_not_records_are_refused(self):
        for bad in (None, [{"name": "A"}], [{"name": "A", "lft": "1", "rgt": 2}]):
            with self.assertRaises(ValueError):
                optical.groups_of(bad, "PP OPT")
        with self.assertRaises(ValueError):
            optical.items_of([{"code": "X"}], "PP OPT")


class Signature(unittest.TestCase):
    def test_verify(self):
        import base64, hashlib, hmac
        raw, ts = b'{"a":1}', str(int(NOW))
        sig = base64.b64encode(hmac.new(b"s", ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(optical.verify(ts, sig, raw, "s", now=NOW), "")
        self.assertTrue(optical.verify(ts, sig, raw, "t", now=NOW))
        self.assertTrue(optical.verify(ts, sig, raw, "s", now=NOW + 301))
        self.assertTrue(optical.verify("x", sig, raw, "s", now=NOW))


if __name__ == "__main__":
    unittest.main()
