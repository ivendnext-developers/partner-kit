"""S24's pure core: the kiosk's code and scan, the shop's date, the Kiosk record, the pricer's arguments and the answer.

    python3 -m unittest discover -s samples/s24_price_checker/tests -p 'test_*.py'
"""

import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import price  # noqa: E402

TODAY = datetime.date(2026, 10, 15)
KIOSK = {"name": "k3v9q0abcd", "title": "Aisle 4", "enabled": 1, "pos_profile": "Store 1", "company": "Demo Retail",
         "selling_price_list": "Standard Selling", "currency": "USD", "customer": "Walk-in", "warehouse": "Store 1 - DR"}


def details(**kw):
    d = {"item_code": "PEN-01", "item_name": "Blue pen", "uom": "Nos", "price_list_rate": 10.0,
         "discount_percentage": 0.0, "discount_amount": 0.0, "pricing_rules": "", "image": ""}
    d.update(kw)
    return d


class Inputs(unittest.TestCase):
    def test_a_kiosk_code_is_the_frameworks_random_name_only(self):
        self.assertEqual(price.kiosk_code(" K3V9Q0ABCD "), "k3v9q0abcd")
        for bad in ("", "k3v9q0abc", "k3v9q0abcde", "../../x/yy", "k3v9q0ab-d", None, 12):
            self.assertIsNone(price.kiosk_code(bad), bad)

    def test_a_scan_is_short_printable_text(self):
        self.assertEqual(price.scan_text(" 4006381333931\n"), "4006381333931")
        for bad in ("", "   ", "x" * 65, "a\x00b", None):
            self.assertIsNone(price.scan_text(bad), repr(bad))

    def test_the_kiosks_date_is_used_within_a_day_else_the_services(self):
        self.assertEqual(price.kiosk_date("2026-10-16", TODAY), "2026-10-16")
        self.assertEqual(price.kiosk_date("2026-10-14", TODAY), "2026-10-14")
        for bad in ("2026-10-18", "2020-01-01", "16/10/2026", "2026-13-01", None, ""):
            self.assertEqual(price.kiosk_date(bad, TODAY), "2026-10-15", bad)


class KioskRecord(unittest.TestCase):
    def test_a_switched_on_complete_kiosk_is_used(self):
        k = price.kiosk_of(KIOSK)
        self.assertEqual((k["selling_price_list"], k["currency"], k["customer"]), ("Standard Selling", "USD", "Walk-in"))

    def test_a_switched_off_kiosk_is_not(self):
        self.assertIsNone(price.kiosk_of(dict(KIOSK, enabled=0)))
        self.assertIsNone(price.kiosk_of(dict(KIOSK, enabled=None)))

    def test_a_kiosk_without_a_price_list_is_not_set_up(self):
        for f in ("selling_price_list", "company", "currency"):
            self.assertIsNone(price.kiosk_of(dict(KIOSK, **{f: None})), f)


class PricerArgs(unittest.TestCase):
    def test_one_unit_in_the_scanned_unit_on_the_stores_list_for_its_walk_in_customer(self):
        a = price.pricer_args(price.kiosk_of(KIOSK), {"item_code": "PEN-01", "uom": "Box", "barcode": "123"}, "2026-10-15")
        self.assertEqual(a, {"item_code": "PEN-01", "qty": 1, "doctype": "Sales Invoice", "company": "Demo Retail",
                             "selling_price_list": "Standard Selling", "currency": "USD", "conversion_rate": 1,
                             "transaction_date": "2026-10-15", "ignore_pricing_rule": 1, "uom": "Box",
                             "customer": "Walk-in", "warehouse": "Store 1 - DR"})

    def test_a_batch_scan_prices_that_batch(self):
        a = price.pricer_args(price.kiosk_of(KIOSK), {"item_code": "MILK", "batch_no": "LOT7"}, "2026-10-15")
        self.assertEqual(a["batch_no"], "LOT7")
        self.assertNotIn("uom", a)

    def test_no_price_rule_is_applied_the_kiosk_shows_the_list_price(self):
        for prof in (KIOSK, dict(KIOSK, ignore_pricing_rule=0)):
            self.assertEqual(price.pricer_args(price.kiosk_of(prof), {"item_code": "PEN-01"}, "2026-10-15")["ignore_pricing_rule"], 1)

    def test_never_a_rate_so_the_shops_pricer_writes_no_price_row(self):
        a = price.pricer_args(price.kiosk_of(KIOSK), {"item_code": "PEN-01", "rate": "5", "price_list_rate": "5", "discount_amount": "1"}, "2026-10-15")
        self.assertFalse({"rate", "price_list_rate", "discount_amount"} & set(a))


class Answer(unittest.TestCase):
    def test_the_list_price_for_one_unit(self):
        a = price.answer_of(details(), KIOSK)
        self.assertEqual((a["status"], a["item"], a["unit"], a["price"], a["currency"]), ("found", "Blue pen", "Nos", 10.0, "USD"))

    def test_a_discount_the_pricer_returns_is_never_shown(self):
        a = price.answer_of(details(discount_percentage=15, discount_amount=1.5, pricing_rules='["PRLE-1"]'), KIOSK)
        self.assertEqual((a["price"], set(a)), (10.0, {"status", "item", "unit", "currency", "price", "image"}))

    def test_no_price_on_the_list_is_never_shown_as_free(self):
        for plr in (0, None, "", -1):
            self.assertEqual(price.answer_of(details(price_list_rate=plr), KIOSK)["status"], "no_price", plr)

    def test_only_a_public_picture_is_shown(self):
        self.assertEqual(price.answer_of(details(image="/files/pen.jpg"), KIOSK)["image"], "/files/pen.jpg")
        for bad in ("/private/files/pen.jpg", "https://elsewhere.example/p.jpg", "/files/a b.jpg", "/files/x\"y", "javascript:x"):
            self.assertIsNone(price.answer_of(details(image=bad), KIOSK)["image"], bad)

    def test_every_refusal_is_a_plain_sentence(self):
        for code, text in price.TEXT.items():
            self.assertEqual(price.refusal(code), {"status": code, "message": text})
            self.assertTrue(text.endswith(".") and "<" not in text and len(text) <= 80, code)


if __name__ == "__main__":
    unittest.main()
