"""S42's rules (copay.py): the add-on's co-pay rules in every combination, the price-list rule, who may buy on cover, returns.

    python3 -m unittest discover -s samples/s42_third_party_payer/tests -p 'test_*.py'

The add-on-shaped fixture: two covered lines, A (gross 600, the shop's discount 60, so 540) and B (gross 400, discount 40,
so 360, with extra-item pay of 2 a unit on 5 units). Covered before the discount 990, after it 890; the sale is 900.
Each case below is worked by hand from the add-on's own case comments (cases 1-8).
"""

import itertools
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import copay as C  # noqa: E402

TODAY = "2026-10-23"


def plan(**kw):
    p = dict(name="P1", title="Generic Plan", payer="GEN", active=1, copay_percent=0, invoice_upper_limit=0,
             max_patient_amount=0, discount_order=C.BEFORE_LIMIT, copay_order=C.BEFORE_DISCOUNT,
             covers=C.FORMULARY_ONLY, no_partial_refund=0,
             formulary=[{"item_code": "A", "covered": 1}, {"item_code": "B", "covered": 1, "extra_pay": 2}])
    p.update(kw)
    return p


MEMBER = dict(name="M1", customer="C1", plan="P1", active=1, valid_from="2026-01-01", valid_to="2026-12-31")


def shaped_sale(**kw):
    r = dict(sale_ref="S1", customer="C1", date=TODAY, precision=2,
             lines=[dict(line_id="1", item_code="A", item_group="Medicine", qty=6, conversion_factor=1, amount=540,
                         discount=60),
                    dict(line_id="2", item_code="B", item_group="Medicine", qty=5, conversion_factor=1, amount=360,
                         discount=40)])
    r.update(kw)
    return r


def split(**pkw):
    a = C.coverage(shaped_sale(), plan(**pkw), MEMBER, False)
    return a["answer"], a["totals"]["payer_share"], a["totals"]["patient_share"]


class AddOnCases(unittest.TestCase):
    """Each case's payer and patient shares, worked by hand (the module docstring's fixture)."""

    def test_case_1_no_copay_no_limit(self):          # the patient pays only the extra-item pay
        self.assertEqual(split(), ("cover", "890.00", "10.00"))

    def test_case_2_copay_before_the_discount(self):  # 20% of 990: the discount is wholly the payer's
        self.assertEqual(split(copay_percent=20), ("cover", "692.00", "208.00"))

    def test_case_3_maximum_patient_amount(self):     # 198 capped at 150
        self.assertEqual(split(copay_percent=20, max_patient_amount=150), ("cover", "740.00", "160.00"))

    def test_case_4_limit_on_the_amount_after_the_discount(self):
        # 700 inside the limit (after the discount) is 778.65 before it; 20% of that is 155.73
        self.assertEqual(split(copay_percent=20, invoice_upper_limit=700), ("cover", "544.27", "355.73"))

    def test_case_5_limit_on_the_amount_before_the_discount(self):
        # 700 before the discount is 629.29 after it; 20% of 700 is 140
        self.assertEqual(split(copay_percent=20, invoice_upper_limit=700, discount_order=C.AFTER_LIMIT),
                         ("cover", "489.29", "410.71"))

    def test_case_6_copay_after_the_discount(self):   # 20% of 890: the patient shares the discount
        self.assertEqual(split(copay_percent=20, copay_order=C.AFTER_DISCOUNT), ("cover", "712.00", "188.00"))

    def test_case_7_after_the_discount_with_a_maximum(self):
        self.assertEqual(split(copay_percent=20, copay_order=C.AFTER_DISCOUNT, max_patient_amount=150),
                         ("cover", "740.00", "160.00"))

    def test_case_8_after_the_discount_with_a_limit(self):
        self.assertEqual(split(copay_percent=20, copay_order=C.AFTER_DISCOUNT, invoice_upper_limit=700),
                         ("cover", "560.00", "340.00"))

    def test_a_limit_above_the_sale_changes_nothing(self):
        self.assertEqual(split(copay_percent=20, invoice_upper_limit=5000), split(copay_percent=20))

    def test_full_copay_leaves_the_payer_nothing(self):
        self.assertEqual(split(copay_percent=100, copay_order=C.AFTER_DISCOUNT), ("cover", "0.00", "900.00"))


GRID = dict(
    copay_percent=(0, 20, 100),
    invoice_upper_limit=(0, 300, 5000),
    max_patient_amount=(0, 25, 10000),
    discount=(0, 50),
    discount_order=(C.BEFORE_LIMIT, C.AFTER_LIMIT),
    copay_order=(C.BEFORE_DISCOUNT, C.AFTER_DISCOUNT),
    extra_pay=(0, Decimal("3.333")),
    uncovered=(0, 1),
    max_qty=(0, 2),
)


def grid_case(copay_percent, invoice_upper_limit, max_patient_amount, discount, discount_order, copay_order, extra_pay,
              uncovered, max_qty):
    p = plan(copay_percent=copay_percent, invoice_upper_limit=invoice_upper_limit,
             max_patient_amount=max_patient_amount, discount_order=discount_order, copay_order=copay_order,
             formulary=[{"item_code": "A", "covered": 1, "extra_pay": extra_pay, "max_qty": max_qty},
                        {"item_group": "Medicine", "covered": 1}, {"item_code": "U", "covered": 0}])
    lines = [dict(line_id="1", item_code="A", item_group="Medicine", qty=3, conversion_factor=1,
                  amount=Decimal("333.33") - discount, discount=discount),
             dict(line_id="2", item_code="B", item_group="Medicine", qty=1, conversion_factor=2,
                  amount=Decimal("120.01"), discount=0)]
    if uncovered:
        lines.append(dict(line_id="3", item_code="U", item_group="Medicine", qty=1, amount=Decimal("45.5"), discount=0))
    return p, shaped_sale(lines=lines)


class EveryCombination(unittest.TestCase):
    """DO-5's first *done when*: the split holds in every rule combination (3·3·3·2·2·2·2·2·2 = 1,728 sales)."""

    def test_every_combination_splits_the_sale_exactly_and_within_the_rules(self):
        n = 0
        for combo in itertools.product(*GRID.values()):
            kw = dict(zip(GRID, combo))
            p, req = grid_case(**kw)
            a = C.coverage(req, p, MEMBER, False)
            with self.subTest(**{k: str(v) for k, v in kw.items()}):
                self.assertEqual(a["answer"], "cover")
                tot = sum(Decimal(str(l["amount"])) for l in req["lines"])
                pay, pat = Decimal(a["totals"]["payer_share"]), Decimal(a["totals"]["patient_share"])
                self.assertEqual(pay + pat, tot)                                     # to the cent, always
                self.assertEqual(sum(Decimal(l["payer_share"]) for l in a["lines"]), pay)
                for l, r in zip(a["lines"], req["lines"]):
                    self.assertGreaterEqual(Decimal(l["payer_share"]), 0)
                    self.assertLessEqual(Decimal(l["payer_share"]), Decimal(str(r["amount"])))
                    self.assertEqual(Decimal(l["payer_share"]) + Decimal(l["patient_share"]), Decimal(str(r["amount"])))
                if uncov := [l for l in a["lines"] if l["item_code"] == "U"]:
                    self.assertEqual(uncov[0]["payer_share"], "0")                   # an uncovered line is the patient's
                    self.assertFalse(uncov[0]["covered"])
                    self.assertTrue(uncov[0]["sellable"])
                rules = a["rules"]
                if kw["max_patient_amount"]:
                    self.assertLessEqual(Decimal(rules["copay"]), Decimal(kw["max_patient_amount"]))
                if kw["invoice_upper_limit"]:
                    self.assertLessEqual(pay, Decimal(kw["invoice_upper_limit"]))
                self.assertLessEqual(pay, Decimal(rules["covered_net"]))
                if kw["copay_percent"] == 100 and not kw["max_patient_amount"]:
                    self.assertEqual(pay, 0)
                n += 1
        self.assertEqual(n, 1728)

    def test_a_higher_copay_never_raises_the_payers_share(self):
        for combo in itertools.product(*[v for k, v in GRID.items() if k != "copay_percent"]):
            kw = dict(zip([k for k in GRID if k != "copay_percent"], combo))
            shares = [Decimal(C.coverage(grid_case(copay_percent=c, **kw)[1], grid_case(copay_percent=c, **kw)[0],
                                         MEMBER, False)["totals"]["payer_share"]) for c in (0, 20, 100)]
            self.assertEqual(shares, sorted(shares, reverse=True), kw)

    def test_a_higher_limit_never_lowers_the_payers_share(self):
        keys = [k for k in GRID if k != "invoice_upper_limit"]
        for combo in itertools.product(*[GRID[k] for k in keys]):
            kw = dict(zip(keys, combo))
            shares = []
            for lim in (300, 5000):
                p, req = grid_case(invoice_upper_limit=lim, **kw)
                shares.append(Decimal(C.coverage(req, p, MEMBER, False)["totals"]["payer_share"]))
            self.assertLessEqual(shares[0], shares[1], kw)

    def test_the_quantity_limit_covers_only_that_many_units(self):
        p, req = grid_case(0, 0, 0, 0, C.BEFORE_LIMIT, C.BEFORE_DISCOUNT, 0, 0, 2)
        line = C.coverage(req, p, MEMBER, False)["lines"][0]
        self.assertEqual((line["covered_qty"], line["qty_limit"], line["reason"]), ("2", "2", "over_limit"))
        self.assertEqual(line["payer_share"], "222.22")   # two of three units of 333.33


class PriceList(unittest.TestCase):
    """A pharmacy's insurer rule: on a plan with a price list, an item off it or at zero on it is not sellable on the cover."""

    def answer(self, prices):
        return C.coverage(shaped_sale(), plan(price_list="Generic Insurer Prices"), MEMBER, False, prices,
                          {"title": "Generic Insurer", "active": 1})

    def test_both_items_listed_and_priced_is_covered(self):
        self.assertEqual(self.answer({"A": 100, "B": 80})["answer"], "cover")

    def test_an_item_off_the_list_is_refused_in_the_payers_words(self):
        a = self.answer({"A": 100})
        self.assertEqual(a["answer"], "refuse")
        b = a["lines"][1]
        self.assertEqual((b["sellable"], b["reason"]), (False, "not_on_list"))
        self.assertEqual(b["message"], "B is not covered by Generic Insurer's price list.")       # VR-29

    def test_an_item_at_zero_on_the_list_is_refused(self):
        a = self.answer({"A": 100, "B": 0})
        self.assertEqual((a["answer"], a["lines"][1]["reason"]), ("refuse", "zero_on_list"))
        self.assertEqual(a["lines"][1]["message"], "B has no price on Generic Insurer's price list.")  # VR-36

    def test_the_lines_own_rate_never_counts(self):
        # the till re-prices a zero row from the store's list: the line carries 360, the payer's list says 0
        self.assertEqual(self.answer({"A": 100, "B": 0})["lines"][1]["sellable"], False)

    def test_a_refused_line_pays_nothing_from_the_payer(self):
        a = self.answer({"A": 100})
        self.assertEqual(a["lines"][1]["payer_share"], "0")

    def test_a_plan_without_a_price_list_never_refuses_on_price(self):
        self.assertEqual(C.coverage(shaped_sale(), plan(), MEMBER, False, {})["answer"], "cover")


class WhoMayBuyOnCover(unittest.TestCase):
    def test_a_barred_customer_is_refused_in_the_brds_words(self):
        a = C.coverage(shaped_sale(), plan(), MEMBER, True, None, {"title": "Generic Insurer", "active": 1})
        self.assertEqual((a["answer"], a["code"]), ("no_cover", "barred"))
        self.assertEqual(a["message"], "C1 cannot buy on Generic Insurer.")                       # VR-30

    def test_no_member_record_is_no_cover(self):
        self.assertEqual(C.coverage(shaped_sale(), plan(), None, False)["code"], "no_member")

    def test_a_member_out_of_date_is_no_cover(self):
        self.assertEqual(C.coverage(shaped_sale(date="2027-01-01"), plan(), MEMBER, False)["code"], "no_member")

    def test_a_member_of_another_plan_is_no_cover(self):
        self.assertEqual(C.coverage(shaped_sale(), plan(name="P2"), MEMBER, False)["code"], "no_member")

    def test_an_inactive_plan_or_payer_is_no_cover(self):
        self.assertEqual(C.coverage(shaped_sale(), plan(active=0), MEMBER, False)["code"], "plan_off")
        self.assertEqual(C.coverage(shaped_sale(), plan(), MEMBER, False, None, {"active": 0})["code"], "plan_off")

    def test_no_cover_puts_the_whole_sale_on_the_patient(self):
        a = C.coverage(shaped_sale(), plan(), None, False)
        self.assertEqual(a["totals"], {"payer_share": "0", "patient_share": "900.00"})

    def test_the_claim_reference_is_the_same_on_every_press(self):
        r1 = C.coverage(shaped_sale(), plan(), MEMBER, False)["claim_ref"]
        self.assertEqual(r1, C.coverage(shaped_sale(), plan(copay_percent=20), MEMBER, False)["claim_ref"])
        self.assertEqual(r1, "GEN-S1")


CLAIM = [{"line_id": "1", "qty": 6, "amount": "540", "payer_share": "427.86"},
         {"line_id": "2", "qty": 5, "amount": "360", "payer_share": "264.14"}]


class Returns(unittest.TestCase):
    def test_a_whole_return_gives_back_every_share(self):
        r = C.return_split(CLAIM, [{"line_id": "1", "qty": 6}, {"line_id": "2", "qty": 5}])
        self.assertEqual(r["totals"], {"payer_back": "692.00", "patient_back": "208.00"})

    def test_a_partial_return_gives_back_its_own_part(self):
        r = C.return_split(CLAIM, [{"line_id": "1", "qty": 3}])
        self.assertEqual(r["lines"][0], {"line_id": "1", "qty": "3", "amount_back": "270.00", "payer_back": "213.93",
                                         "patient_back": "56.07"})

    def test_returns_one_unit_at_a_time_add_up_to_the_sale(self):
        earlier, pay = [], Decimal(0)
        for _ in range(6):
            r = C.return_split(CLAIM, [{"line_id": "1", "qty": 1}], earlier)
            line = r["lines"][0]
            earlier.append(dict(line_id="1", qty=1, payer_back=line["payer_back"], amount_back=line["amount_back"]))
            pay += Decimal(line["payer_back"])
        self.assertEqual(pay, Decimal("427.86"))
        self.assertEqual(sum(Decimal(e["amount_back"]) for e in earlier), Decimal(540))

    def test_three_returns_of_a_third_add_up_to_the_cent(self):
        claim = [{"line_id": "1", "qty": 3, "amount": "100", "payer_share": "100"}]
        earlier = []
        for _ in range(3):
            line = C.return_split(claim, [{"line_id": "1", "qty": 1}], earlier)["lines"][0]
            earlier.append(dict(line_id="1", qty=1, payer_back=line["payer_back"], amount_back=line["amount_back"]))
        self.assertEqual([e["payer_back"] for e in earlier], ["33.33", "33.33", "33.34"])

    def test_no_partial_refund_refuses_part_of_a_sale(self):
        r = C.return_split(CLAIM, [{"line_id": "1", "qty": 6}], no_partial_refund=True)
        self.assertEqual((r["answer"], r["code"]), ("refuse", "partial_return"))
        r = C.return_split(CLAIM, [{"line_id": "1", "qty": 3}, {"line_id": "2", "qty": 5}], no_partial_refund=True)
        self.assertEqual(r["code"], "partial_return")

    def test_no_partial_refund_lets_the_whole_sale_back(self):
        r = C.return_split(CLAIM, [{"line_id": "1", "qty": 6}, {"line_id": "2", "qty": 5}], no_partial_refund=True)
        self.assertEqual(r["answer"], "cover")

    def test_more_than_the_sale_holds_is_refused(self):
        earlier = [dict(line_id="1", qty=6, payer_back="427.86", amount_back="540")]
        self.assertEqual(C.return_split(CLAIM, [{"line_id": "1", "qty": 1}], earlier)["code"], "over_return")
        self.assertEqual(C.return_split(CLAIM, [{"line_id": "9", "qty": 1}])["code"], "unknown_line")


class PlanCheck(unittest.TestCase):
    def test_a_good_plan_passes(self):
        self.assertEqual(C.check_plan(plan()), [])

    def test_each_bad_setting_is_named(self):
        bad = C.check_plan(plan(copay_percent=120, invoice_upper_limit=-1, discount_order="x", copay_order="y",
                                covers="z", formulary=[{"item_code": "A", "item_group": "G"}, {"item_code": "B",
                                                                                                "extra_pay": -1}]))
        self.assertEqual(len(bad), 7)


if __name__ == "__main__":
    unittest.main()
