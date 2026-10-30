"""S61's core rules: the share (blank is the consignor's, outside 0 to 100 refused), each line's part to the cent and
exact, the lines other payouts hold, and the pay check's words.

    python3 -m unittest discover -s samples/s61_consignment_payouts/tests -p 'test_*.py'
"""

import datetime
import os
import sys
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import consign  # noqa: E402

D = Decimal


class Share(unittest.TestCase):
    def test_blank_or_zero_is_the_consignors_own(self):
        for v in (None, "", 0, "0", 0.0):
            self.assertIsNone(consign.share_of(v), v)

    def test_a_share_outside_0_to_100_or_not_a_number_is_refused(self):
        for v in (-1, 100.01, "x", True, [40]):
            with self.assertRaises(ValueError, msg=v):
                consign.share_of(v)
        self.assertEqual(consign.share_of(100), D(100))


class Part(unittest.TestCase):
    def test_to_the_cent_half_away_from_zero_a_return_the_same_negative(self):
        self.assertEqual(consign.payout_amount(D("10.05"), D(50)), D("5.03"))
        self.assertEqual(consign.payout_amount(D("-10.05"), D(50)), D("-5.03"))
        self.assertEqual(consign.payout_amount(D("33.33"), D("33.3")), D("11.10"))

    def test_money_is_exact_never_a_float_rounding(self):
        self.assertEqual(consign.money(0.1), D("0.1"))
        self.assertEqual(consign.money("19.99"), D("19.99"))
        for v in (None, True, "x", float("nan"), {"a": 1}):
            self.assertIsNone(consign.money(v), v)


def line(name, item="A", amount=100.0, typ="POS Invoice", parent="S1"):
    return {"sale_type": typ, "name": name, "parent": parent, "item_code": item, "item_name": item, "qty": 1,
            "base_net_amount": amount}


HEAD = {"docstatus": 1, "company": "Co", "posting_date": "2026-10-01", "is_return": 0, "is_consolidated": 0}


class WorkOut(unittest.TestCase):
    def owed(self, lines, heads, holds=None, items=None, share=40, up_to="2026-10-31", settled=None):
        return consign.work_out(share, items or {"A": {"share": 0}}, lines, heads, holds or {}, settled or [], "Co",
                                datetime.date.fromisoformat(up_to))

    def test_only_a_submitted_line_of_the_company_on_or_before_the_date(self):
        heads = {("POS Invoice", "S1"): HEAD, ("POS Invoice", "S2"): dict(HEAD, company="X"),
                 ("POS Invoice", "S3"): dict(HEAD, posting_date="2026-11-01"), ("POS Invoice", "S4"): dict(HEAD, docstatus=0),
                 ("Sales Invoice", "S5"): dict(HEAD, is_consolidated=1), ("Sales Invoice", "S6"): HEAD}
        rows, why = self.owed([line("a"), line("b", parent="S2"), line("c", parent="S3"), line("d", parent="S4"),
                               line("e", typ="Sales Invoice", parent="S5"), line("f", typ="Sales Invoice", parent="S6"),
                               line("g", item="Q")], heads)
        self.assertEqual((why, [r["sale_line"] for r in rows]), ("", ["a", "f"]))

    def test_only_a_desk_invoice_is_judged_by_its_combined_flag(self):
        heads = {("POS Invoice", "S1"): dict(HEAD, is_consolidated=1)}     # a till sale has no such field: never read
        self.assertEqual(len(self.owed([line("a")], heads)[0]), 1)

    def test_a_held_line_is_left_and_a_cancelled_sale_settles_its_paid_balance_once(self):
        self.assertEqual(self.owed([line("a")], {("POS Invoice", "S1"): HEAD}, {"a": "CSG-P-00010"})[0], [])
        paid = [{"sale_row": "a", "sale_line": "a", "sale_type": "POS Invoice", "sale": "S1", "kind": "Sale",
                 "item_code": "A", "sale_amount": 100, "share": 40, "payout": 40, "posting_date": "2026-10-01"}]
        cancelled = {("POS Invoice", "S1"): dict(HEAD, docstatus=2)}
        rows = self.owed([line("a")], cancelled, {"a": "CSG-P-00001"}, settled=paid)[0]
        self.assertEqual([(r["sale_line"], r["kind"], r["sale_amount"], r["payout"]) for r in rows],
                         [("a/1", consign.TAKEN_BACK, D(-100), D(-40))])
        back = dict(paid[0], sale_line="a/1", kind=consign.TAKEN_BACK, sale_amount=-100, payout=-40)
        self.assertEqual(self.owed([line("a")], cancelled, {"a": "CSG-P-00001"}, settled=paid + [back])[0], [])   # settled: 0
        rows = self.owed([], cancelled, settled=[back])[0]                     # the payout that paid it cancelled since
        self.assertEqual([(r["sale_line"], r["kind"], r["payout"]) for r in rows], [("a/1", consign.CORRECTION, D(40))])
        self.assertEqual(self.owed([], {("POS Invoice", "S1"): HEAD}, settled=paid)[0], [])  # not cancelled: nothing

    def test_a_sale_before_consigned_since_is_never_theirs(self):
        heads = {("POS Invoice", "S1"): HEAD, ("POS Invoice", "S2"): dict(HEAD, posting_date="2026-09-30")}
        rows, _ = consign.work_out(40, {"A": {"share": 0}}, [line("a"), line("b", parent="S2")], heads, {}, [], "Co",
                                   datetime.date(2026, 10, 31), datetime.date(2026, 10, 1))
        self.assertEqual([r["sale_line"] for r in rows], ["a"])

    def test_the_consignors_share_must_be_set_and_in_range(self):
        heads = {("POS Invoice", "S1"): HEAD}
        self.assertIn("has no share yet", self.owed([line("a")], heads, share=0)[1])
        self.assertIn("must be a percent", self.owed([line("a")], heads, share=140)[1])
        self.assertIn("on item A", self.owed([line("a")], heads, items={"A": {"share": -5}})[1])


class Holds(unittest.TestCase):
    def test_a_cancelled_payout_and_this_payout_hold_nothing(self):
        rows = [{"parent": "CSG-P-00001", "sale_line": "a"}, {"parent": "CSG-P-00002", "sale_line": "b"}, {"parent": "CSG-P-00003", "sale_line": "c"},
                {"parent": "CSG-P-00009", "sale_line": "d"}]
        got = consign.holds_of(rows, {"CSG-P-00001": consign.DRAFT, "CSG-P-00002": consign.CANCELLED, "CSG-P-00003": consign.PAID}, "CSG-P-00001")
        self.assertEqual(got, {"c": "CSG-P-00003"})

    def test_a_paid_payout_wins_over_a_draft_holding_the_same_line(self):
        rows = [{"parent": "CSG-P-00021", "sale_row": "a"}, {"parent": "CSG-P-00022", "sale_row": "a"},
                {"parent": "CSG-P-00021", "sale_row": "b"}]
        states = {"CSG-P-00021": consign.DRAFT, "CSG-P-00022": consign.PAID}
        for order in (rows, rows[::-1]):
            self.assertEqual(consign.holds_of(order, states, "CSG-P-00030"), {"a": "CSG-P-00022", "b": "CSG-P-00021"})


class PayCheck(unittest.TestCase):
    def setUp(self):
        self.owed = [{"sale_type": "POS Invoice", "sale": "S1", "sale_row": "a", "sale_line": "a", "kind": "Sale", "item_code": "A",
                      "sale_amount": D(100), "share": D(40), "payout": D(40)}]
        self.p = {"workflow_state": consign.DRAFT, "paid_with": "Cash", "paid_on": "2026-10-31", "payout_total": 40.0,
                  "sales_total": 100.0,
                  "lines": [{"sale_type": "POS Invoice", "sale": "S1", "sale_row": "a", "sale_line": "a", "kind": "Sale", "item_code": "A",
                             "sale_amount": 100.0, "share": 40.0, "payout": 40.0}]}
        self.lock = {"enabled": 1, "mode": "refuse"}

    def test_a_payout_that_matches_may_be_paid(self):
        self.assertEqual(consign.check_to_pay(self.p, self.owed, {}, self.lock), "")

    def test_the_stored_amounts_are_compared_to_the_cent(self):
        self.p["lines"][0]["payout"] = 40.004
        self.assertEqual(consign.check_to_pay(self.p, self.owed, {}, self.lock), "")
        self.p["lines"][0]["payout"] = 40.01
        self.assertIn("has changed", consign.check_to_pay(self.p, self.owed, {}, self.lock))

    def test_a_paid_or_cancelled_payout_is_never_paid_again(self):
        for st in (consign.PAID, consign.CANCELLED):
            self.p["workflow_state"] = st
            self.assertIn("Only a draft", consign.check_to_pay(self.p, self.owed, {}, self.lock))

    def test_no_lines_no_pay(self):
        self.p["lines"] = []
        self.assertIn("no lines", consign.check_to_pay(self.p, self.owed, {}, self.lock))


if __name__ == "__main__":
    unittest.main()
