"""S22's money rules, each with the value it must give. tests/canaries.py breaks each rule and expects these to fail."""

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
import money  # noqa: E402


class Money(unittest.TestCase):
    def test_amounts_are_decimal_and_round_half_up(self):
        e = money.earned("100.25", 2, 2)            # 2.005 → 2.01 (half-up; banker's rounding would give 2.00)
        self.assertIsInstance(e, Decimal)
        self.assertEqual(e, Decimal("2.01"))
        self.assertEqual(money.earned(0.1 + 0.2, 100, 2), Decimal("0.30"))   # a float from the API goes through str

    def test_precision_follows_the_currency(self):
        self.assertEqual(money.earned("10.0125", 50, 3), Decimal("5.006"))   # 5.00625 → 5.006 at 3 places (three-decimal currencies)
        self.assertEqual(money.earned("10.0125", 50, 0), Decimal("5"))

    def test_nothing_earned_on_zero_or_negative(self):
        self.assertEqual(money.earned(-50, 2, 2), Decimal("0.00"))

    def test_the_value_leaves_out_gift_cards_and_the_base_the_goods_tender_discount(self):
        items = [{"transaction_mode": "Sale", "amount": 100, "net_amount": 90, "custom_tender_discount_apportioned": 4},
                 {"transaction_mode": "Gift Certificate", "amount": 50, "net_amount": 45,
                  "custom_tender_discount_apportioned": 2}]                        # 10% off the sale, 6 tender discount
        sale = {"grand_total": "135", "items": items, "custom_tender_discount_amount": "6"}
        self.assertEqual(money.goods_value(sale), Decimal("90"))                  # 135 − 45
        self.assertEqual(money.earn_base(sale), Decimal("86"))                    # 90 − (6 − 2)
        payout = {"grand_total": "-25", "items": [{"transaction_mode": "Gift Certificate Cashback", "net_amount": -25}]}
        self.assertEqual(money.goods_value(payout), Decimal("0"))                 # a pay-out rides alone and earns nothing

    def test_a_partial_return_reverses_its_share(self):
        # earned 20.00 on 1000.00; 333.33 returned → 6.6666 → 6.67
        self.assertEqual(money.reversal("20.00", "1000", 0, "333.33", 0, 2), Decimal("6.67"))

    def test_the_last_return_takes_exactly_what_is_left(self):
        e, total = Decimal("20.00"), Decimal("1000")
        first = money.reversal(e, total, 0, "333.33", 0, 2)
        second = money.reversal(e, total, "333.33", "333.33", first, 2)
        third = money.reversal(e, total, "666.66", "333.34", first + second, 2)
        self.assertEqual(first + second + third, e)                       # 6.67 + 6.67 + 6.66

    def test_total_reversed_never_exceeds_what_was_earned(self):
        # a return worth more than is left (rounding, or a return of the whole sale after a partial one)
        self.assertEqual(money.reversal("20.00", "1000", "500", "600", "19.99", 2), Decimal("0.01"))
        self.assertEqual(money.reversal("20.00", "1000", 0, "999.99", "20.00", 2), Decimal("0.00"))
        # 99 returns of 5.00 on a 1000.00 sale that earned 1.00 each took 0.005 → 0.01 (half-up): 0.99 is gone, so a
        # further return of 400.00 takes the 0.01 left, not its 0.40 share
        self.assertEqual(money.reversal("1.00", "1000", "495", "400", "0.99", 2), Decimal("0.01"))

    def test_a_cancellation_reverses_the_rest(self):
        self.assertEqual(money.cancellation("20.00", "6.67", 2), Decimal("13.33"))
        self.assertEqual(money.cancellation("20.00", "25", 2), Decimal("0.00"))


if __name__ == "__main__":
    unittest.main()
