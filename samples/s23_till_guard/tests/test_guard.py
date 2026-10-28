"""S23's rules (``guard.on_check``, ``guard.on_scan``, ``guard.settings_of``): each rule bites, each is off until set,
and every sentence is plain text the till accepts.

    python3 -m unittest discover -s samples/s23_till_guard/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import guard  # noqa: E402

SETTINGS = {"name": "Default", "lowest_unit_price": 0.01, "max_qty_per_line": 50, "approval_from": 5000,
            "approval_answer": "approve", "confirm_question": ""}


def line(n, code="BREAD", qty=1, rate=1250, group="Bakery"):
    return {"line_no": n, "item_code": code, "item_group": group, "qty_milli": round(qty * 1000), "uom": "Nos",
            "rate_minor": rate, "amount_minor": round(rate * qty), "discount_minor": 0, "line_attributes": []}


def context(lines=None, grand=None, stage="sale", exp=2, currency="AED"):
    lines = lines if lines is not None else [line(1)]
    grand = grand if grand is not None else sum(x["amount_minor"] for x in lines)
    return {"v": 1, "point": "check", "stage": stage, "currency_exponent": exp, "sale_ref": "s-1", "store": "Main - S",
            "pos_profile": "Mall", "company": "Shop", "currency": currency, "lang": "en", "operator": "c@shop.example",
            "customer": "CUST-1", "customer_group": "Retail", "price_list": "Standard Selling", "coupon_codes": [],
            "sale_attributes": [], "lines": lines,
            "totals": {"net_minor": grand, "tax_minor": 0, "discount_minor": 0, "grand_minor": grand},
            "offered_tenders": ["Cash", "Credit Card"]}


def scan(code="PEN-01"):
    return {"v": 1, "point": "capture", "event": "scan", "sale_ref": "s-1", "store": "Main - S", "pos_profile": "Mall",
            "operator": "c@shop.example", "customer": None, "lang": "en",
            "line": {"item_code": code, "item_group": "Stationery", "qty_milli": 1000, "uom": "Nos", "batch_no": "",
                     "serial_no": "", "scanned_code": code}}


class CheckRules(unittest.TestCase):
    rules = guard.settings_of(SETTINGS)

    def test_an_ordinary_sale_is_allowed(self):
        self.assertEqual(guard.on_check(context(), self.rules), {"verdict": "allow"})

    def test_a_line_at_the_placeholder_price_is_refused_in_our_words(self):
        out = guard.on_check(context([line(1), line(2, "PEN-01", rate=1)]), self.rules)
        self.assertEqual(out, {"verdict": "refuse",
                               "reason": "Line 2: PEN-01 is priced 0.01 AED. Correct its price before the sale is paid."})

    def test_a_free_line_priced_zero_is_never_refused(self):
        self.assertEqual(guard.on_check(context([line(1), line(2, "GIFT", rate=0)]), self.rules), {"verdict": "allow"})

    def test_a_line_just_above_the_placeholder_price_is_allowed(self):
        self.assertEqual(guard.on_check(context([line(1, rate=2)]), self.rules)["verdict"], "allow")

    def test_more_than_the_most_on_one_line_is_refused(self):
        out = guard.on_check(context([line(1, "WATER-24", qty=60, rate=10)]), self.rules)
        self.assertEqual(out, {"verdict": "refuse", "reason": "Line 1: 60 of WATER-24. The most on one line is 50."})

    def test_exactly_the_most_is_allowed(self):
        self.assertEqual(guard.on_check(context([line(1, "WATER-24", qty=50, rate=10)]), self.rules)["verdict"], "allow")

    def test_a_large_sale_calls_a_manager(self):
        out = guard.on_check(context([line(1, "TV", rate=500000)]), self.rules)
        self.assertEqual(out, {"verdict": "approve", "reason": "Sales of 5,000.00 AED or more need a manager's approval."})

    def test_just_below_the_approval_amount_is_allowed(self):
        self.assertEqual(guard.on_check(context([line(1, "TV", rate=499999)]), self.rules)["verdict"], "allow")

    def test_the_shop_may_choose_a_question_instead_of_a_manager(self):
        rules = guard.settings_of(dict(SETTINGS, approval_answer="ask"))
        out = guard.on_check(context([line(1, "TV", rate=500000)]), rules)
        self.assertEqual(out, {"verdict": "ask", "question": "This sale is 5,000.00 AED or more. Has a manager agreed to it?"})

    def test_a_refusal_comes_before_the_approval(self):
        out = guard.on_check(context([line(1, "TV", rate=500000), line(2, "PEN-01", rate=1)]), self.rules)
        self.assertEqual(out["verdict"], "refuse")

    def test_what_a_return_takes_back_is_never_judged(self):
        self.assertEqual(guard.on_check(context([line(1, "PEN-01", qty=-1, rate=1)], stage="return"), self.rules),
                         {"verdict": "allow"})

    def test_an_exchanges_sold_line_at_the_placeholder_price_is_refused(self):
        out = guard.on_check(context([line(1, "TV", qty=-1, rate=90000), line(2, "PEN-01", rate=1)], stage="return"),
                             self.rules)
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn("PEN-01", out["reason"])

    def test_an_exchanges_sold_line_over_the_most_is_refused(self):
        out = guard.on_check(context([line(1, "TV", qty=-1), line(2, "WATER-24", qty=60)], stage="return"), self.rules)
        self.assertEqual(out["verdict"], "refuse")

    def test_an_exchange_that_takes_a_large_payment_calls_a_manager(self):
        big = context([line(1, "PEN-01", qty=-1, rate=10), line(2, "TV", rate=900000)], stage="return", grand=899990)
        self.assertEqual(guard.on_check(big, self.rules)["verdict"], "approve")

    def test_an_exchange_judged_on_what_it_takes_not_what_it_sells(self):
        even = context([line(1, "TV", qty=-1, rate=890000), line(2, "TV-2", rate=900000)], stage="return", grand=10000)
        self.assertEqual(guard.on_check(even, self.rules), {"verdict": "allow"})

    def test_an_exchanges_returned_line_is_not_judged(self):
        returned = line(1, "WATER-24", qty=-60, rate=1)
        self.assertEqual(guard.on_check(context([returned, line(2)], grand=1250), self.rules), {"verdict": "allow"})

    def test_the_currencys_own_digits(self):
        kwd = guard.on_check(context([line(1, "PEN-01", rate=10)], exp=3, currency="KWD"), self.rules)
        self.assertEqual(kwd["reason"], "Line 1: PEN-01 is priced 0.010 KWD. Correct its price before the sale is paid.")
        jpy = guard.on_check(context([line(1, "TV", rate=5000)], exp=0, currency="JPY"), self.rules)
        self.assertEqual(jpy, {"verdict": "approve", "reason": "Sales of 5,000 JPY or more need a manager's approval."})

    def test_no_settings_record_means_every_rule_is_off(self):
        rules = guard.settings_of(None)
        ctx = context([line(1, "PEN-01", qty=500, rate=1)], grand=10 ** 9)
        self.assertEqual(guard.on_check(ctx, rules), {"verdict": "allow"})

    def test_blank_zero_negative_and_unreadable_numbers_switch_a_rule_off(self):
        for v in (None, "", 0, -5, "abc"):
            rules = guard.settings_of({"lowest_unit_price": v, "max_qty_per_line": v, "approval_from": v})
            self.assertEqual(guard.on_check(context([line(1, "PEN-01", qty=500, rate=1)], grand=10 ** 9), rules),
                             {"verdict": "allow"}, v)

    def test_a_blank_or_unknown_approval_answer_asks_the_cashier(self):
        # ask works with no further setting; approve needs the check's May-approve tick (else the answer is not used)
        for v in ("maybe", None, ""):
            self.assertEqual(guard.settings_of(dict(SETTINGS, approval_answer=v))["approval_answer"], "ask", v)

    def test_every_sentence_is_plain_and_at_most_140(self):
        rules = guard.settings_of(dict(SETTINGS, confirm_question="<b>Check</b> " + "x" * 300))
        long = "<script>" + "W" * 200
        for out in (guard.on_check(context([line(1, long, rate=1)]), rules),
                    guard.on_check(context([line(1, long, qty=99, rate=10)]), rules),
                    guard.on_scan(scan(long), rules)):
            text = out.get("reason") or out.get("question")
            self.assertTrue(1 <= len(text) <= guard.TEXT_MAX, text)
            self.assertFalse(set(text) & {"<", ">"}, text)


class LinesAndLowestPrices(unittest.TestCase):
    """1.3.0: the most lines on one sale, and a line below its item's lowest price (the retailer's price list)."""
    rules = guard.settings_of(dict(SETTINGS, approval_from=0, max_lines_per_sale=3, lowest_price_list="Lowest"))
    LOW = {("BREAD", "Nos"): 10.0, ("BREAD", "Box"): 100.0}

    def test_more_lines_than_the_most_are_refused_and_exactly_the_most_allowed(self):
        three = [line(n) for n in (1, 2, 3)]
        self.assertEqual(guard.on_check(context(three), self.rules), {"verdict": "allow"})
        out = guard.on_check(context(three + [line(4)]), self.rules)
        self.assertEqual(out, {"verdict": "refuse",
                               "reason": "This sale has 4 lines. The most on one sale is 3. Ring the rest as a second sale."})

    def test_what_a_return_takes_back_is_not_counted(self):
        lines = [line(1), line(2), line(3), line(4, qty=-1)]
        self.assertEqual(guard.on_check(context(lines, stage="return"), self.rules), {"verdict": "allow"})

    def test_a_line_below_its_lowest_price_calls_a_manager(self):
        out = guard.on_check(context([line(1, rate=999)]), self.rules, self.LOW)
        self.assertEqual(out, {"verdict": "approve", "reason":
                               "Line 1: BREAD is 9.99 AED, below its lowest price of 10.00 AED. It needs a manager's approval."})

    def test_at_its_lowest_price_is_allowed(self):
        self.assertEqual(guard.on_check(context([line(1, rate=1000)]), self.rules, self.LOW), {"verdict": "allow"})

    def test_the_line_is_judged_in_its_own_unit(self):
        box = dict(line(1, rate=9000), uom="Box")
        self.assertEqual(guard.on_check(context([box]), self.rules, self.LOW)["verdict"], "approve")
        self.assertEqual(guard.on_check(context([dict(box, rate_minor=10000)]), self.rules, self.LOW), {"verdict": "allow"})

    def test_a_unit_with_no_row_for_a_priced_item_calls_a_manager(self):
        pair = dict(line(1, rate=100000), uom="Pair")             # never a way round the item's lowest price
        self.assertEqual(guard.on_check(context([pair]), self.rules, self.LOW), {"verdict": "approve", "reason":
                         "Line 1: BREAD is sold in Pair, which has no lowest price. It needs a manager's approval."})
        other = line(1, "MILK", rate=1)                            # an item with no row at all is not judged
        self.assertEqual(guard.on_check(context([other]), dict(self.rules, lowest_price=0), self.LOW), {"verdict": "allow"})

    def test_a_discount_on_the_whole_sale_counts(self):
        ctx = context([line(1, rate=1000)])
        ctx["totals"].update(net_minor=500, discount_minor=500)   # a 50% discount on the sale: the customer pays 5.00
        self.assertEqual(guard.on_check(ctx, self.rules, self.LOW), {"verdict": "approve", "reason":
                         "Line 1: BREAD is 5.00 AED after the sale's discount, below its lowest price of 10.00 AED. "
                         "It needs a manager's approval."})

    def test_a_line_exactly_at_its_lowest_after_the_sale_discount_is_allowed(self):
        ctx = context([line(1, "BREAD", rate=43)])
        ctx["totals"].update(net_minor=115, discount_minor=100)     # 43 x 115 / 215 is exactly 23
        self.assertEqual(guard.on_check(ctx, dict(self.rules, lowest_price=0), {("BREAD", "Nos"): 0.23}), {"verdict": "allow"})

    def test_a_lowest_price_is_never_rounded_down(self):
        self.assertEqual(guard.on_check(context([line(1, rate=12)]), dict(self.rules, lowest_price=0),
                                        {("BREAD", "Nos"): 0.125})["verdict"], "approve")

    def test_the_most_lines_stays_under_what_the_check_is_sent(self):
        self.assertEqual(guard.settings_of(dict(SETTINGS, max_lines_per_sale=600))["max_lines"], 499)

    def test_a_free_line_is_never_judged(self):
        self.assertEqual(guard.on_check(context([line(1, rate=0)]), self.rules, self.LOW), {"verdict": "allow"})

    def test_the_retailer_may_choose_a_question_and_more_lines_are_counted(self):
        rules = dict(self.rules, approval_answer="ask")
        out = guard.on_check(context([line(1, rate=500), line(2, rate=1500), line(3, rate=900)]), rules, self.LOW)
        self.assertEqual(out, {"verdict": "ask", "question": "Line 1: BREAD is 5.00 AED, below its lowest price of 10.00 AED."
                                                            " 1 more line is below theirs. Has a manager agreed to it?"})

    def test_a_large_sale_below_its_lowest_price_is_one_approval_naming_both(self):
        rules = dict(self.rules, approval_from=50.0)
        out = guard.on_check(context([line(1, qty=6, rate=999)]), rules, self.LOW)
        self.assertEqual(out["verdict"], "approve")
        self.assertIn("below its lowest price of 10.00 AED. The sale is 50.00 AED or more.", out["reason"])

    def test_a_refusal_comes_before_a_lowest_price_approval(self):
        out = guard.on_check(context([line(1, rate=999), line(2, rate=1)]), self.rules, self.LOW)
        self.assertEqual(out["verdict"], "refuse")

    def test_off_until_set(self):
        rules = guard.settings_of(SETTINGS)
        self.assertEqual((rules["max_lines"], rules["lowest_list"]), (0, ""))
        many = [line(n, rate=999) for n in range(1, 30)]
        self.assertEqual(guard.on_check(context(many), dict(rules, approval_from=0)), {"verdict": "allow"})

    def test_lowest_prices_are_picked_as_the_engine_picks_a_dated_price(self):
        rows = [{"item_code": "BREAD", "uom": "Nos", "price_list_rate": 12, "currency": "AED", "valid_from": "2025-01-01"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 8, "currency": "AED", "valid_from": "2026-01-01"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 10, "currency": "AED", "valid_from": "2026-10-01"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 99, "currency": "AED", "valid_from": "2026-11-01"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 50, "currency": "USD", "valid_from": "2026-10-25"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 60, "currency": "AED", "customer": "CUST-1", "valid_from": "2026-10-25"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 70, "currency": "AED", "batch_no": "B1", "valid_from": "2026-10-25"},
                {"item_code": "BREAD", "uom": "Nos", "price_list_rate": 80, "currency": "AED", "supplier": "S1", "valid_from": "2026-10-25"},
                {"item_code": "MILK", "uom": "Nos", "price_list_rate": 3, "currency": "AED", "valid_upto": "2026-10-27"},
                {"item_code": "JAM", "uom": "Nos", "price_list_rate": 0, "currency": "AED"}, "not a row"]
        self.assertEqual(guard.lowest_prices(rows, "AED", "2026-10-28"), {("BREAD", "Nos"): 10.0})

    def test_every_new_sentence_is_plain_and_at_most_140(self):
        code = "X" * 60 + "<b>"
        low = {(code, "Nos"): 10.0}
        rules = dict(self.rules, approval_from=1.0, approval_answer="ask")
        for out in (guard.on_check(context([line(1, code, rate=999), line(2, code, rate=500)]), rules, low),
                    guard.on_check(context([line(n, code) for n in range(1, 9)]), rules, low)):
            text = out.get("reason") or out.get("question")
            self.assertLessEqual(len(text), 140)
            self.assertNotIn("<", text)
            if out["verdict"] == "ask":                     # the explanation is shortened, never the question
                self.assertTrue(text.endswith("Has a manager agreed to it?"))
        self.assertEqual(out["verdict"], "refuse")


class ScanRule(unittest.TestCase):
    def test_a_flagged_item_beeps_and_asks_the_default_question(self):
        self.assertEqual(guard.on_scan(scan(), guard.settings_of(SETTINGS)),
                         {"verdict": "confirm", "question": "PEN-01: Check this item before it goes on the sale. Add it?"})

    def test_the_shops_own_question(self):
        rules = guard.settings_of(dict(SETTINGS, confirm_question="Fragile. Has it been checked for damage?"))
        self.assertEqual(guard.on_scan(scan(), rules)["question"], "PEN-01: Fragile. Has it been checked for damage?")


class Shapes(unittest.TestCase):
    def test_a_check_with_a_line_missing_its_price_is_not_read(self):
        ctx = context()
        del ctx["lines"][0]["rate_minor"]
        with self.assertRaises(ValueError):
            guard.check_context({"point": "check/1", "context": ctx})

    def test_a_customer_add_is_not_this_apps_event(self):
        ctx = scan()
        ctx["event"] = "customer_add"
        with self.assertRaises(ValueError):
            guard.scan_context({"point": "capture/1", "context": ctx})

    def test_the_wrong_point_is_not_read(self):
        with self.assertRaises(ValueError):
            guard.check_context({"point": "capture/1", "context": context()})
        with self.assertRaises(ValueError):
            guard.scan_context({"point": "check/1", "context": scan()})



def batch_scan(code="MILK-1", batch=""):
    ctx = scan(code)
    ctx["line"]["batch_no"] = batch
    return ctx


class ShelfWarning(unittest.TestCase):
    """*Warn of a shorter-dated batch*: a notice naming the batch to sell first, else allow."""

    def test_off_until_the_shop_sets_it(self):
        self.assertFalse(guard.settings_of(SETTINGS)["shelf_warning"])
        self.assertTrue(guard.settings_of(dict(SETTINGS, warn_shorter_shelf_life=1))["shelf_warning"])

    def test_a_scanned_batch_with_a_sooner_one_in_the_store_is_warned(self):
        dated = [("2026-12-01", "B-LATE"), ("2026-11-02", "B-SOON")]
        self.assertEqual(guard.on_scan_shelf(batch_scan(batch="B-LATE"), dated),
                         {"verdict": "notice", "message": "MILK-1: batch B-SOON expires sooner (2026-11-02). Sell it first."})

    def test_the_soonest_batch_scanned_is_not_warned(self):
        dated = [("2026-12-01", "B-LATE"), ("2026-11-02", "B-SOON")]
        self.assertEqual(guard.on_scan_shelf(batch_scan(batch="B-SOON"), dated), {"verdict": "allow"})

    def test_a_scan_naming_no_batch_names_the_one_to_sell_first(self):
        dated = [("2026-12-01", "B-LATE"), ("2026-11-02", "B-SOON")]
        self.assertEqual(guard.on_scan_shelf(batch_scan(), dated),
                         {"verdict": "notice", "message": "MILK-1: sell batch B-SOON first. It expires 2026-11-02."})

    def test_one_expiry_date_or_no_batch_is_not_warned(self):
        self.assertEqual(guard.on_scan_shelf(batch_scan(), [("2026-11-02", "B-1"), ("2026-11-02", "B-2")]), {"verdict": "allow"})
        self.assertEqual(guard.on_scan_shelf(batch_scan(), []), {"verdict": "allow"})
        self.assertEqual(guard.on_scan_shelf(batch_scan(batch="B-GONE"), [("2026-11-02", "B-1")]), {"verdict": "allow"})


if __name__ == "__main__":
    unittest.main()
