"""S25's rules (service/gcs.py): what counts as spend, how many cards it earns, who may earn.

    python3 -m unittest discover -s samples/s25_gift_on_spend/tests -p 'test_*.py'
"""

import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
import gcs  # noqa: E402
from fake_shop import SETTINGS  # noqa: E402

S = gcs.Settings(SETTINGS)


def sale(**kw):
    d = dict(name="S1", docstatus=1, is_return=0, transaction_mode="Sale", currency="ZAR", customer="C1",
             grand_total=1200, items=[], payments=[])
    d.update(kw)
    return d


class Spend(unittest.TestCase):
    def test_spend_is_the_grand_total_tax_included(self):
        self.assertEqual(gcs.spend(sale(grand_total=1150.5)), Decimal("1150.5"))

    def test_a_gift_card_sold_on_the_sale_does_not_count(self):
        items = [{"amount": 900, "transaction_mode": "Sale"}, {"amount": 300, "transaction_mode": "Gift Certificate"}]
        self.assertEqual(gcs.spend(sale(grand_total=1200, items=items)), Decimal(900))

    def test_what_a_gift_card_or_store_credit_paid_does_not_count(self):
        pays = [{"type": "Gift Certificate", "amount": 150}, {"type": "Store Credit", "amount": 50},
                {"type": "Cash", "amount": 1000}]
        self.assertEqual(gcs.spend(sale(grand_total=1200, payments=pays)), Decimal(1000))

    def test_spend_is_never_below_zero(self):
        self.assertEqual(gcs.spend(sale(grand_total=100, payments=[{"type": "Gift Certificate", "amount": 300}])), 0)

    def test_a_returns_spend_is_its_value_whatever_it_was_refunded_to(self):
        ret = {"grand_total": -460, "items": [{"amount": -400, "transaction_mode": "Sale Return"}],
               "payments": [{"type": "Store Credit", "amount": -460}]}
        self.assertEqual(gcs.return_spend(ret), Decimal(460))          # the till's return lines, tax included

    def test_an_item_return_line_in_a_sale_counts_with_its_own_sign(self):
        items = [{"amount": -1200, "transaction_mode": "Item Return"}, {"amount": 1250, "transaction_mode": "Sale"}]
        self.assertEqual(gcs.spend(sale(grand_total=50, items=items)), Decimal(50))

    def test_a_gift_card_paid_out_or_recharged_on_the_sale_does_not_count(self):
        items = [{"amount": 900, "transaction_mode": "Sale"}, {"amount": 200, "transaction_mode": "Gift Certificate Recharge"},
                 {"amount": -100, "transaction_mode": "Gift Certificate Cashback"}]
        self.assertEqual(gcs.spend(sale(grand_total=1000, items=items)), Decimal(900))

    def test_loyalty_points_and_what_is_owed_do_not_count(self):
        self.assertEqual(gcs.spend(sale(grand_total=1200, loyalty_amount=150, outstanding_amount=50)), Decimal(1000))

    def test_a_sale_on_account_earns_nothing_on_that_part(self):
        # the engine's shape: an On Account tender row, counted as paid, outstanding 0
        pays = [{"type": "On Account", "amount": 1200}]
        self.assertEqual(gcs.spend(sale(grand_total=1200, payments=pays, outstanding_amount=0)), Decimal(0))

    def test_a_partner_wallet_earns_nothing_and_a_negative_tender_row_is_ignored(self):
        self.assertEqual(gcs.spend(sale(grand_total=1200, payments=[{"type": "Wallet", "amount": 300}])), Decimal(900))
        pays = [{"type": "Cash", "amount": 1300}, {"type": "On Account", "amount": -100}]
        self.assertEqual(gcs.spend(sale(grand_total=1200, payments=pays)), Decimal(1200))

    def test_a_return_takes_off_what_was_refunded_after_its_tender_discount(self):
        ret = {"grand_total": -100, "items": [{"amount": -100, "transaction_mode": "Sale Return"}],
               "custom_tender_discount_amount": -5}
        self.assertEqual(gcs.return_spend(ret), Decimal(95))

    def test_a_tender_discount_is_not_money_paid(self):
        self.assertEqual(gcs.spend(sale(grand_total=1000, custom_tender_discount_amount=50)), Decimal(950))

    def test_kept_is_what_the_net_still_earns_never_more_than_issued(self):
        self.assertEqual([gcs.kept(n, 1000, 2) for n in (-5, 999, 1000, 2500, 9000)], [0, 0, 1, 2, 2])


class Cards(unittest.TestCase):
    def test_none_below_the_threshold_one_at_it(self):
        self.assertEqual([gcs.cards_for(x, S) for x in (999.99, 1000, 2500)], [0, 1, 1])

    def test_one_per_full_threshold_up_to_the_shops_cap(self):
        s = gcs.Settings(dict(SETTINGS, max_cards_per_sale=3))
        self.assertEqual([gcs.cards_for(x, s) for x in (1999, 2000, 3500, 99000)], [1, 2, 3, 3])

    def test_compared_at_the_currencys_precision(self):
        self.assertEqual(gcs.cards_for("999.995", S), 1)        # rounds half-up to 1000.00 at 2 places
        self.assertEqual(gcs.cards_for("999.994", S), 0)

    def test_a_cap_of_0_or_nothing_is_one_card(self):
        self.assertEqual(gcs.Settings(dict(SETTINGS, max_cards_per_sale=0)).max_cards, 1)


class WhoEarns(unittest.TestCase):
    def test_a_plain_booked_sale_for_a_known_customer_earns(self):
        self.assertEqual(gcs.why_no_card(sale(), S, "Individual"), "")

    def test_these_never_earn(self):
        cases = {"a walk-in": sale(customer="Walk-in — Demo"), "a walk-in ": sale(customer=""),
                 "an excluded customer group": sale(customer="STAFF1"), "a return": sale(is_return=1),
                 "transaction mode Layaway": sale(transaction_mode="Layaway"),
                 "another currency": sale(currency="USD"), "not a booked sale": sale(docstatus=2)}
        for why, s in cases.items():
            group = "Staff" if s["customer"] == "STAFF1" else "Individual"
            self.assertEqual(gcs.why_no_card(s, S, group), why.strip(), why)


class Ready(unittest.TestCase):
    def test_the_settings_say_why_they_cannot_issue(self):
        self.assertEqual(S.why_not_ready(), "")
        for change, why in (({"enabled": 0}, "switched off"), ({"currency": ""}, "no currency"),
                            ({"threshold": 0}, "more than 0"), ({"card_value": 0}, "more than 0"),
                            ({"card_item": ""}, "no gift card item"), ({"hold_hours": -1}, "negative")):
            self.assertIn(why, gcs.Settings(dict(SETTINGS, **change)).why_not_ready(), change)

    def test_no_settings_record_is_switched_off(self):
        self.assertIn("switched off", gcs.Settings(None).why_not_ready())

    def test_a_hold_of_0_is_kept_not_defaulted(self):
        self.assertEqual(gcs.Settings(dict(SETTINGS, hold_hours=0)).hold_hours, 0)
        self.assertEqual(gcs.Settings({k: v for k, v in SETTINGS.items() if k != "hold_hours"}).hold_hours, 24)

    def test_the_gift_card_item_must_not_turn_into_money(self):
        ok = dict(custom_is_gift_card=1, disabled=0, custom_recharge=0, custom_cashback=0, custom_use_as_store_credit=0,
                  custom_expiry_days=0)
        self.assertEqual(gcs.why_not_item(ok, S), "")
        for change, why in (({"custom_recharge": 1}, "rechargeable"), ({"custom_cashback": 1}, "cash"),
                            ({"custom_use_as_store_credit": 1}, "store credit"), ({"custom_is_gift_card": 0}, "not an enabled"),
                            ({"custom_expiry_days": 1}, "expires before the hold")):
            self.assertIn(why, gcs.why_not_item(dict(ok, **change), S), change)
        self.assertEqual(gcs.why_not_item(dict(ok, custom_expiry_days=2), S), "")
        self.assertIn("not an enabled", gcs.why_not_item(None, S))

    def test_a_card_is_named_by_its_sale_and_position(self):
        self.assertEqual(gcs.card_key("ACC-PSINV-1", 2), "ACC-PSINV-1:2")


if __name__ == "__main__":
    unittest.main()
