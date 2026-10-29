"""S56's pure core: the code's signature, the door's keys and the kiosk's code, a choice's price, the order's checks,
and the QR code (its grids pinned from the framework's own QR library, which drew the same codes on the bench)."""

import hashlib
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE)]
import gor  # noqa: E402
import qr  # noqa: E402

S = [b"new", b"old"]
LINK = ("https://guest-ordering.ivendnext.app/#s=demo-2.sandbox.ivend.co&t=IVN-GOR-CODE-00012.3."
        "AbCdEfGhIjKlMnOpQrStUv")
# sha256 of the grid as rows of 0/1, for texts whose grid the framework's QR library (pyqrcode, on the bench :8115,
# 2026-10-29) drew equal to this encoder's at the mask it chose: versions 4, 7 and 10
PINNED = {"x" * 60: (33, "8903ac311430c993d9b007375bfcfe3c8a9735cdafc677760d013660f42b96d5"),
          LINK: (45, "f082785663df29b12fbbaa85a8de1d2580742a6e4d569be531f260fd7410d930"),
          "z" * 200: (57, "156c30f88b7728938114861d36146a2dec80ee623404bd108fe5bac818f0e4c8")}


def grid_hash(m):
    return hashlib.sha256("\n".join("".join("1" if c else "0" for c in row) for row in m).encode()).hexdigest()


class Rules(unittest.TestCase):
    def test_r1_a_code_is_the_retailers_own_signature_for_that_record_and_number(self):
        t = gor.link_of("https://p.example", "shop.example.com", "GOR-CODE-00001", 3, b"new").split("&t=")[1]
        self.assertEqual(gor.code_of("shop.example.com", t, S), ("GOR-CODE-00001", 3))
        self.assertEqual(gor.code_of("shop.example.com", t, [b"old"]), None)
        self.assertEqual(gor.code_of("other.example.com", t, S), None)
        rec, n, sig = t.rsplit(".", 2)
        for bad in (f"GOR-CODE-00002.{n}.{sig}", f"{rec}.4.{sig}", f"{rec}.0.{gor.sign(b'new', 'shop.example.com', rec, 0)}",
                    f"{rec}.{n}", f"{rec}.x.{sig}", None, 7, "a" * 201):
            self.assertIsNone(gor.code_of("shop.example.com", bad, S), bad)

    def test_r2_the_link_carries_its_token_after_the_hash(self):
        link = gor.link_of("https://p.example/", "shop.example.com", "GOR-CODE-00001", 1, b"k")
        self.assertTrue(link.startswith("https://p.example/#s=shop.example.com&t=GOR-CODE-00001.1."))

    def test_r3_the_doors_keys_are_the_same_for_a_retry_and_new_for_each_step(self):
        k = "6f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a"
        self.assertEqual(gor.door_key(k, "open"), gor.door_key(k, "open"))
        self.assertNotEqual(gor.door_key(k, "open"), gor.door_key(k, "add"))
        self.assertNotEqual(gor.door_key(k, "add"), gor.door_key(k[:-1] + "b", "add"))
        self.assertRegex(gor.door_key(k, "add"), r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-a[0-9a-f]{3}-[0-9a-f]{12}$")

    def test_r4_the_kiosk_code_is_four_letters_that_cannot_be_misread(self):
        codes = {gor.kiosk_code(f"key-{i:04d}-0000000000000") for i in range(500)}
        self.assertGreater(len(codes), 490)
        for c in codes:
            self.assertEqual(len(c), 4)
            self.assertFalse(set(c) & set("01OIL"), c)
        self.assertEqual(gor.kiosk_code("abc-0000000000000000"), gor.kiosk_code("abc-0000000000000000"))

    def test_r5_a_choices_price_is_the_rows_amount_else_the_list_price_less_its_discount(self):
        self.assertEqual(gor.choice_price({"price_type": "Amount", "price": 0.6}, 9), 0.6)
        self.assertEqual(gor.choice_price({"price_type": "System Generated", "price": 5}, 0.8), 0.8)
        self.assertEqual(gor.choice_price({"price_type": "", "discount_type": "Percentage", "discount": 25}, 4), 3.0)
        self.assertEqual(gor.choice_price({"price_type": "Amount", "price": 2, "discount_type": "Amount", "discount": 0.5}, None), 1.5)
        self.assertIsNone(gor.choice_price({"price_type": ""}, None))

    def test_r6_a_note_is_one_line_of_text_at_most_eighty_characters(self):
        self.assertEqual(gor.clean_note("no\tonions\n​please‮"), "no onions please")
        self.assertEqual(len(gor.clean_note("x" * 200)), gor.NOTE_MAX)
        self.assertEqual(gor.clean_note(7), "")

    def test_r7_the_stores_limits_have_their_defaults_and_bounds(self):
        self.assertEqual(gor.setting(None, gor.LINES), 10)
        self.assertEqual(gor.setting(200, gor.LINES), 50)
        self.assertEqual(gor.setting(-3, gor.QTY), 1)

    def test_r8_what_a_code_was_made_for(self):
        self.assertEqual(gor.made_for({"kind": "Table", "store": "S", "place": "P", "kiosk_name": "K"}), "Table|S|P")
        self.assertEqual(gor.made_for({"kind": "Kiosk", "store": "S", "place": "P", "kiosk_name": " Door "}), "Kiosk|S|Door")

    def test_r9_a_group_switched_off_and_an_ordinary_offer_are_no_choice(self):
        items = [{"name": "TEA", "item_name": "Tea", "item_group": "Drinks"}]
        rows = [{"parent": "TEA", "idx": 1, "item_code": "LEMON", "custom_mpos_option_group": "Off"},
                {"parent": "TEA", "idx": 2, "item_code": "CAKE", "custom_mpos_option_group": None}]
        menu = gor.menu_of(items, rows, {"Off": {"name": "Off", "enabled": 0}}, {"TEA": 2})
        self.assertEqual(gor.dishes_of(menu)["TEA"]["groups"], [])

    # ── the QR code ──
    def test_q1_the_grid_has_the_standards_size_and_finders(self):
        for text, (size, _) in PINNED.items():
            m = qr.matrix(text)
            self.assertEqual(len(m), size)
            for x0, y0 in ((0, 0), (size - 7, 0), (0, size - 7)):
                self.assertTrue(all(m[y0][x0 + i] and m[y0 + 6][x0 + i] for i in range(7)))   # the finder's frame
                self.assertFalse(m[y0 + 1][x0 + 1])
                self.assertTrue(m[y0 + 3][x0 + 3])

    def test_q2_the_grids_the_framework_drew_the_same(self):
        for text, (_, want) in PINNED.items():
            self.assertEqual(grid_hash(qr.matrix(text)), want, text[:20])

    def test_q3_a_text_too_long_is_refused_and_the_picture_is_an_svg_address(self):
        with self.assertRaises(ValueError):
            qr.matrix("x" * 214)
        self.assertTrue(qr.svg_data_uri("hello").startswith("data:image/svg+xml;base64,"))


if __name__ == "__main__":
    unittest.main()
