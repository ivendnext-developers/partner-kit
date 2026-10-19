"""S25's card life against a stand-in shop (service/cards.py): issue at 0, release once after the hold, void on a cancel
or a return, never a second card or a second balance.

    python3 -m unittest discover -s samples/s25_gift_on_spend/tests -p 'test_*.py'
"""

import datetime as dt
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
import cards  # noqa: E402
from fake_shop import sale, shop  # noqa: E402
from shop import ShopError  # noqa: E402

T0 = dt.datetime(2026, 10, 15, 8, 0, tzinfo=dt.timezone.utc)
HOUR = dt.timedelta(hours=1)


def book(t, name="S1", now=T0, **kw):
    sale(t, name, **kw)
    return cards.on_sale(t, cards.load_settings(t), name, now)


def only_card(t):
    (rec,) = t.db["PP GCS Card"].values()
    return rec


class Issue(unittest.TestCase):
    def test_a_sale_over_the_threshold_earns_one_card_held_at_0(self):
        t = shop()
        self.assertEqual(book(t)["cards"], ["Held"])
        rec = t.card("S1:1")
        gc = t.db["Gift Card"][rec["card_number"]]
        self.assertEqual((rec["status"], rec["gift_card"], rec["customer"], rec["sale"]), ("Held", gc["name"], "C1", "S1"))
        self.assertEqual((gc["balance"], gc["total"], gc["item_code"], gc["first_name"]), ("0", "100", "PROMO-GIFT", "C1 name"))
        self.assertRegex(rec["card_number"], r"^[1-9]\d{15}$")
        self.assertEqual(rec["release_after"], "2026-10-16 10:00:00")          # the shop's clock + 24 h
        self.assertEqual(rec["release_after_utc"], "2026-10-16T08:00:00Z")     # this service's clock + 24 h

    def test_below_the_threshold_and_the_excluded_earn_nothing(self):
        for kw in ({"grand_total": 999}, {"customer": "Walk-in — Demo"}, {"customer": "STAFF1"},
                   {"transaction_mode": "Layaway"}, {"currency": "USD"}):
            t = shop()
            book(t, **kw)
            self.assertNotIn("PP GCS Card", t.db, kw)
            self.assertNotIn("Gift Card", t.db, kw)

    def test_the_sales_own_customer_group_is_used_when_it_has_one(self):
        t = shop()
        book(t, customer_group="Staff")
        self.assertNotIn("PP GCS Card", t.db)

    def test_one_card_per_full_threshold_up_to_the_cap(self):
        t = shop(max_cards_per_sale=3)
        self.assertEqual(book(t, grand_total=3500)["cards"], ["Held"] * 3)
        self.assertEqual(sorted(t.db["PP GCS Card"]), ["S1:1", "S1:2", "S1:3"])
        self.assertEqual(len({r["card_number"] for r in t.db["PP GCS Card"].values()}), 3)

    def test_switched_off_or_unfinished_settings_issue_nothing(self):
        for change in ({"enabled": 0}, {"card_item": ""}):
            t = shop(**change)
            self.assertIn("result", book(t))
            self.assertNotIn("PP GCS Card", t.db)

    def test_a_replayed_sale_earns_no_second_card(self):
        t = shop()
        book(t)
        book(t)
        self.assertEqual(len(t.db["PP GCS Card"]), 1)
        self.assertEqual(len(t.db["Gift Card"]), 1)

    def test_a_crash_after_the_card_record_issues_one_card_on_the_retry(self):
        t = shop()
        t.fail_after_insert = "PP GCS Card"
        with self.assertRaises(SystemExit):
            book(t)
        self.assertEqual(only_card(t)["status"], "Issuing")
        book(t)
        self.assertEqual((only_card(t)["status"], len(t.db["Gift Card"])), ("Held", 1))

    def test_a_crash_after_the_gift_card_finds_it_on_the_retry(self):
        t = shop()
        t.fail_after_insert = "Gift Card"
        with self.assertRaises(SystemExit):
            book(t)
        book(t)
        self.assertEqual((only_card(t)["status"], len(t.db["Gift Card"])), ("Held", 1))

    def test_a_number_already_in_the_shop_is_never_reused(self):
        t = shop()
        t.put("Gift Card", "1000000000000007", balance=50, total=50)
        with mock.patch.object(cards.secrets, "randbelow", side_effect=[7, 8]):
            book(t)
        self.assertEqual(only_card(t)["card_number"], "1000000000000008")
        self.assertEqual(t.db["Gift Card"]["1000000000000007"]["balance"], 50)

    def test_a_gift_card_that_is_not_ours_at_0_is_review_not_held(self):
        t = shop()
        with mock.patch.object(cards, "new_number", return_value="1111222233334444"):
            sale(t, "S1")
            t.fail_after_insert = "PP GCS Card"
            with self.assertRaises(SystemExit):
                cards.on_sale(t, cards.load_settings(t), "S1", T0)
        t.put("Gift Card", "1111222233334444", balance=75, total=75)       # someone else's card took the number
        book(t)
        self.assertEqual(only_card(t)["status"], "Review")
        self.assertEqual(t.db["Gift Card"]["1111222233334444"]["balance"], 75)


class Release(unittest.TestCase):
    def test_nothing_is_released_before_the_hold_has_passed(self):
        t = shop()
        book(t)
        self.assertEqual(cards.release_due(t, T0 + 24 * HOUR - dt.timedelta(seconds=1)), [])
        self.assertEqual(only_card(t)["status"], "Held")

    def test_after_the_hold_one_balance_entry_sets_the_card_to_its_value(self):
        t = shop()
        book(t)
        self.assertEqual(cards.release_due(t, T0 + 24 * HOUR), [("S1:1", "Released")])
        rec = only_card(t)
        (entry,) = t.balance_entries(rec["card_number"])
        self.assertEqual((entry["balance"], entry["docstatus"], rec["balance_entry"]), ("100", 1, entry["name"]))
        self.assertEqual(t.db["Gift Card"][rec["card_number"]]["balance"], 100.0)
        cards.release_due(t, T0 + 48 * HOUR)
        self.assertEqual(len(t.balance_entries(rec["card_number"])), 1)

    def test_the_hold_is_the_one_the_card_was_issued_with(self):
        t = shop(hold_hours=2)
        t.fail_after_insert = "PP GCS Card"
        with self.assertRaises(SystemExit):
            book(t)                                            # the card record holds 2 h; the gift card is not made yet
        t.db["PP GCS Settings"]["Default"]["hold_hours"] = 48  # the shop changes the hold before the retry
        book(t)
        self.assertEqual(cards.release_due(t, T0 + 2 * HOUR), [("S1:1", "Released")])

    def test_a_crash_after_the_balance_entry_never_writes_a_second(self):
        t = shop()
        book(t)
        t.fail_after_insert = "Gift Card Balance"
        with self.assertRaises(SystemExit):
            cards.release_due(t, T0 + 25 * HOUR)
        self.assertEqual(only_card(t)["status"], "Held")
        t.db["Gift Card"][only_card(t)["card_number"]]["balance"] = 40.0        # the customer has spent 60 since
        self.assertEqual(cards.release_due(t, T0 + 26 * HOUR), [("S1:1", "Released")])
        self.assertEqual(len(t.balance_entries(only_card(t)["card_number"])), 1)
        self.assertEqual(t.db["Gift Card"][only_card(t)["card_number"]]["balance"], 40.0)    # never put back

    def test_a_balance_changed_in_the_shop_during_the_hold_is_review(self):
        t = shop()
        book(t)
        t.db["Gift Card"][only_card(t)["card_number"]]["balance"] = 30.0
        self.assertEqual(cards.release_due(t, T0 + 25 * HOUR), [("S1:1", "Review")])
        self.assertEqual(t.balance_entries(only_card(t)["card_number"]), [])

    def test_a_card_that_expired_during_the_hold_is_review(self):
        t = shop()
        book(t)
        t.db["Gift Card"][only_card(t)["card_number"]]["expired"] = 1
        self.assertEqual(cards.release_due(t, T0 + 25 * HOUR), [("S1:1", "Review")])


class Void(unittest.TestCase):
    def test_a_cancel_during_the_hold_voids_and_the_card_is_never_released(self):
        t = shop()
        book(t)
        sale(t, "S1", docstatus=2)
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Voided")])
        self.assertEqual(cards.release_due(t, T0 + 30 * HOUR), [])
        self.assertEqual(t.balance_entries(only_card(t)["card_number"]), [])

    def test_a_cancel_after_the_release_sets_an_unspent_card_to_0(self):
        t = shop()
        book(t)
        cards.release_due(t, T0 + 25 * HOUR)
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Voided")])
        rec = only_card(t)
        self.assertEqual(t.db["Gift Card"][rec["card_number"]]["balance"], 0.0)
        self.assertEqual([e["balance"] for e in t.balance_entries(rec["card_number"])], ["100", "0"])
        self.assertEqual(rec["void_entry"], t.balance_entries(rec["card_number"])[1]["name"])

    def test_a_card_already_spent_is_review_and_keeps_its_balance(self):
        t = shop()
        book(t)
        cards.release_due(t, T0 + 25 * HOUR)
        t.db["Gift Card"][only_card(t)["card_number"]]["balance"] = 35.0
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Review")])
        self.assertEqual(t.db["Gift Card"][only_card(t)["card_number"]]["balance"], 35.0)

    def test_a_cancel_after_a_lost_release_record_still_sets_the_card_to_0(self):
        t = shop()
        book(t)
        t.fail_after_insert = "Gift Card Balance"
        with self.assertRaises(SystemExit):
            cards.release_due(t, T0 + 25 * HOUR)                  # released in the shop; the record still says Held
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Voided")])
        self.assertEqual(t.db["Gift Card"][only_card(t)["card_number"]]["balance"], 0.0)

    def test_a_return_below_the_threshold_voids_and_one_above_keeps(self):
        t = shop()
        book(t, grand_total=1200)
        sale(t, "R1", grand_total=-150, is_return=1, return_against="S1")
        self.assertEqual(cards.on_return(t, "R1")["cards"], [])                  # 1050 left: kept
        sale(t, "R2", grand_total=-100, is_return=1, return_against="S1")
        self.assertEqual(cards.on_return(t, "R2")["cards"], [("S1:1", "Voided")])  # 950 left: voided

    def test_a_return_voids_the_last_cards_first(self):
        t = shop(max_cards_per_sale=3)
        book(t, grand_total=3200)
        sale(t, "R1", grand_total=-1500, is_return=1, return_against="S1")
        self.assertEqual(cards.on_return(t, "R1")["cards"], [("S1:3", "Voided"), ("S1:2", "Voided")])
        self.assertEqual(t.card("S1:1")["status"], "Held")

    def test_a_cancelled_return_gives_no_card_back_and_changes_nothing(self):
        t = shop()
        book(t)
        sale(t, "R1", grand_total=-1200, is_return=1, return_against="S1")
        cards.on_return(t, "R1")
        sale(t, "R1", grand_total=-1200, is_return=1, return_against="S1", docstatus=2)
        self.assertIn("no card is given back", cards.on_cancel(t, "R1")["result"])
        self.assertEqual(only_card(t)["status"], "Voided")


class Folds(unittest.TestCase):
    """The Tier-S review's findings, each pinned (APPF run 3)."""

    def test_a_till_return_with_tax_voids_the_card(self):
        t = shop()
        book(t, grand_total=1150, items=[{"amount": 1000, "transaction_mode": "Sale"}])       # 1000 + 15% tax
        sale(t, "R1", grand_total=-1150, items=[{"amount": -1000}], is_return=1, return_against="S1")
        self.assertEqual(t.db["POS Invoice"]["R1"]["items"][0]["transaction_mode"], "Sale Return")
        self.assertEqual(cards.on_return(t, "R1")["cards"], [("S1:1", "Voided")])

    def test_an_exchange_earns_on_the_net_paid_only(self):
        t = shop()
        items = [{"amount": -1200, "transaction_mode": "Item Return"}, {"amount": 1250, "transaction_mode": "Sale"}]
        self.assertEqual(book(t, grand_total=50, items=items)["result"], "0 card(s)")

    def test_a_sale_handled_after_its_return_earns_only_what_its_net_earns(self):
        t = shop(max_cards_per_sale=3)
        sale(t, "S1", grand_total=3000)
        sale(t, "R1", grand_total=-2500, is_return=1, return_against="S1")
        self.assertEqual(cards.on_return(t, "R1")["result"], "no card on that sale")    # the sale's own event had failed
        self.assertEqual(cards.on_sale(t, cards.load_settings(t), "S1", T0)["cards"], [])   # 500 left: no card

    def test_a_release_reads_the_sale_again_and_voids_a_cancelled_one(self):
        t = shop()
        book(t)
        sale(t, "S1", docstatus=2)                      # cancelled; its own event failed and waits in the feed
        self.assertEqual(cards.release_due(t, T0 + 25 * HOUR), [("S1:1", "Voided")])
        self.assertEqual(t.balance_entries(only_card(t)["card_number"]), [])

    def test_a_release_reads_the_returns_too(self):
        t = shop()
        book(t)
        sale(t, "R1", grand_total=-1200, is_return=1, return_against="S1")
        self.assertEqual(cards.release_due(t, T0 + 25 * HOUR), [("S1:1", "Voided")])

    def test_loyalty_points_and_on_account_earn_nothing(self):
        t = shop()
        self.assertEqual(book(t, grand_total=1500, loyalty_amount=600)["result"], "0 card(s)")
        t = shop()
        pays = [{"type": "Cash", "amount": 600}, {"type": "On Account", "amount": 900}]
        self.assertEqual(book(t, grand_total=1500, payments=pays, outstanding_amount=0)["result"], "0 card(s)")

    def test_a_card_used_then_zeroed_by_staff_is_review_never_this_apps_void(self):
        t = shop()
        book(t)
        cards.release_due(t, T0 + 25 * HOUR)
        number = only_card(t)["card_number"]
        t.redeemed.add(number)                          # spent 60 at the till
        t.db["Gift Card"][number]["balance"] = 40.0
        t.insert({"doctype": "Gift Card Balance", "gift_card": number, "balance": "0", "docstatus": 1})   # staff zero it
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Review")])

    def test_a_void_cut_short_by_a_restart_finishes_as_its_own_void(self):
        t = shop()
        book(t)
        cards.release_due(t, T0 + 25 * HOUR)
        t.fail_after_insert = "Gift Card Balance"
        with self.assertRaises(SystemExit):
            cards.on_cancel(t, "S1")                      # the zero entry landed; the record still says Released
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Voided")])
        self.assertEqual(len(t.balance_entries(only_card(t)["card_number"])), 2)

    def test_a_gift_card_item_that_could_turn_into_money_issues_nothing(self):
        for item in ({"custom_recharge": 1}, {"custom_cashback": 1}, {"custom_use_as_store_credit": 1},
                     {"custom_is_gift_card": 0}, {"disabled": 1}, {"custom_expiry_days": 1}):
            t = shop(item=item)
            self.assertNotIn("PP GCS Card", t.db, item) if "item" in book(t)["result"] else self.fail(item)

    def test_a_card_used_at_the_till_is_never_voided_even_at_full_balance(self):
        t = shop()
        book(t)
        cards.release_due(t, T0 + 25 * HOUR)
        t.redeemed.add(only_card(t)["card_number"])     # spent, then recharged back to its value
        self.assertEqual(cards.on_cancel(t, "S1")["cards"], [("S1:1", "Review")])
        self.assertEqual(len(t.balance_entries(only_card(t)["card_number"])), 1)


class Errors(unittest.TestCase):
    def test_a_shop_that_refuses_a_read_fails_the_event_so_the_feed_keeps_it(self):
        t = shop()
        sale(t, "S1")
        with mock.patch.object(t, "get", side_effect=ShopError(403, "no read on Gift Card")):
            with self.assertRaises(ShopError):
                cards.on_sale(t, cards.load_settings(t), "S1", T0)


if __name__ == "__main__":
    unittest.main()
