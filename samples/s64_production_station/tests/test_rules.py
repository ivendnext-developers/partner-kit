"""S64's pure rules (``pst.py``): the colour of a day, the price points, the read-back check, a cart's lines and stock
entries, the production report's rows, and the signed link.

    python3 -m unittest discover -s samples/s64_production_station/tests -p 'test_*.py'
"""

import datetime
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import pst  # noqa: E402

D = datetime.date
SETTINGS = {"first_week": "2026-11-02", "colours": [{"colour": "Green", "idx": 2}, {"colour": "Blue", "idx": 1},
                                                   {"colour": "Pink", "idx": 3}]}


class Colours(unittest.TestCase):
    def test_the_colours_turn_each_week_in_the_leads_order_and_start_again(self):
        got = [pst.colour_of(SETTINGS, D(2026, 11, 2) + datetime.timedelta(days=d)) for d in (0, 6, 7, 13, 14, 21, 22)]
        self.assertEqual([c for c, _ in got], ["Blue", "Blue", "Green", "Green", "Pink", "Blue", "Blue"])
        self.assertEqual([w.isoformat() for _, w in got],
                         ["2026-11-02", "2026-11-02", "2026-11-09", "2026-11-09", "2026-11-16", "2026-11-23", "2026-11-23"])

    def test_a_day_before_the_first_week_counts_back(self):
        self.assertEqual(pst.colour_of(SETTINGS, D(2026, 11, 1)), ("Pink", D(2026, 10, 26)))

    def test_the_leads_colour_for_one_day_wins_on_that_day_only(self):
        s = dict(SETTINGS, day_colour="Orange", day_colour_on="2026-11-04")
        self.assertEqual(pst.colour_of(s, D(2026, 11, 4)), ("Orange", D(2026, 11, 4)))
        self.assertEqual(pst.colour_of(s, D(2026, 11, 5)), ("Blue", D(2026, 11, 2)))

    def test_no_rotation_no_colour(self):
        self.assertIsNone(pst.colour_of({"colours": [], "first_week": "2026-11-02"}, D(2026, 11, 2)))
        self.assertIsNone(pst.colour_of({"colours": [{"colour": "Blue"}]}, D(2026, 11, 2)))

    def test_the_weeks_a_report_covers_and_the_one_day_colour(self):
        s = dict(SETTINGS, day_colour="Orange", day_colour_on="2026-11-11")
        got = pst.weeks_between(s, D(2026, 11, 4), D(2026, 11, 16))
        self.assertEqual(got, [("Blue", D(2026, 11, 2)), ("Green", D(2026, 11, 9)), ("Orange", D(2026, 11, 11)),
                               ("Pink", D(2026, 11, 16))])

    def test_a_colour_weeks_sold_window_ends_at_its_next_turn_or_today(self):
        self.assertEqual(pst.sold_window(D(2026, 11, 2), 3, D(2026, 12, 31)), (D(2026, 11, 2), D(2026, 11, 22)))
        self.assertEqual(pst.sold_window(D(2026, 11, 2), 3, D(2026, 11, 10)), (D(2026, 11, 2), D(2026, 11, 10)))


class Settings(unittest.TestCase):
    def test_price_points_by_category_to_the_cent_each_once(self):
        s = {"price_points": [{"category": "Tops", "price": 4.99, "idx": 1}, {"category": "Tops", "price": "4.990", "idx": 2},
                              {"category": "Tops", "price": 19.99, "idx": 3}, {"category": "Shirts", "price": 6.99, "idx": 4},
                              {"category": "", "price": 1, "idx": 5}, {"category": "Tops", "price": 0, "idx": 6}]}
        self.assertEqual(pst.price_points(s), {"Tops": [4.99, 19.99], "Shirts": [6.99]})

    def test_the_price_a_tap_names_must_be_the_categorys_own(self):
        pts = {"Tops": [4.99, 19.99], "Shirts": [6.99]}
        self.assertEqual(pst.price_of(pts, "Tops", "19.99"), 19.99)
        self.assertEqual(pst.price_of(pts, "Tops", 19.990001), 19.99)
        for cat, p in (("Tops", 6.99), ("Tops", 5), ("Hats", 4.99), ("Tops", True), ("Tops", None), (None, 4.99)):
            self.assertIsNone(pst.price_of(pts, cat, p), (cat, p))

    def test_only_active_workers_each_once(self):
        s = {"workers": [{"worker_name": "Ana", "active": 1}, {"worker_name": "Ben", "active": 0},
                         {"worker_name": "Ana", "active": 1}, {"worker_name": " ", "active": 1}]}
        self.assertEqual(pst.workers(s), ["Ana"])

    def test_places_and_the_tag_size(self):
        s = {"places": [{"warehouse": "W1", "label": ""}, {"warehouse": "W1", "label": "x"}, {"warehouse": "W2", "label": "Two"}],
             "tag_width_mm": 0, "tag_height_mm": 500}
        self.assertEqual(pst.places(s), [{"warehouse": "W1", "label": "W1"}, {"warehouse": "W2", "label": "Two"}])
        self.assertEqual(pst.tag_size(s), {"width_mm": 50, "height_mm": 100})


class Tags(unittest.TestCase):
    ITEM = {"name": "TOPS-BLU", "mask": "M", "barcodes": ["70102"]}

    def test_the_item_of_a_colour_with_its_barcodes(self):
        rows = [{"name": "B", "pp_pst_tag_colour": "Blue", "custom_barcode_mask": "M", "barcode": "1"},
                {"name": "B", "pp_pst_tag_colour": "Blue", "custom_barcode_mask": "M", "barcode": "2"},
                {"name": "A", "pp_pst_tag_colour": "blue", "custom_barcode_mask": "", "barcode": None},
                {"name": "C", "pp_pst_tag_colour": "Green", "custom_barcode_mask": "M", "barcode": "3"}]
        self.assertEqual(pst.item_for(rows, "Blue"), {"name": "A", "mask": "", "barcodes": []})
        self.assertEqual(pst.item_for(rows[:2], "BLUE"), {"name": "B", "mask": "M", "barcodes": ["1", "2"]})
        self.assertIsNone(pst.item_for(rows, "Pink"))

    def test_a_barcode_read_back_as_its_item_and_price_passes(self):
        ok = {"barcode_masked": True, "item_barcode": "70102", "scanned_price": 19.99}
        self.assertTrue(pst.read_back(ok, self.ITEM, 19.99))
        self.assertTrue(pst.read_back({"barcode_masked": True, "item_code": "TOPS-BLU", "scanned_price": 4.99}, self.ITEM, 4.99))

    def test_the_old_engines_price_and_any_other_item_is_refused(self):
        for got in ({"barcode_masked": True, "item_barcode": "70102", "scanned_price": 999.98},
                    {"barcode_masked": True, "item_barcode": "70103", "scanned_price": 19.99},
                    {"barcode_masked": False, "item_barcode": "70102", "scanned_price": 19.99},
                    {"barcode_masked": True, "item_barcode": "70102", "scanned_price": 19.99, "error": "x"},
                    {"barcode_masked": True, "item_barcode": "70102", "scanned_price": "x"}, None):
            self.assertFalse(pst.read_back(got, self.ITEM, 19.99), got)


class Carts(unittest.TestCase):
    def test_lines_by_item_and_a_taken_back_tag_is_never_received(self):
        tags = [{"item": "B", "quantity": 1, "void": 0}, {"item": "A", "quantity": 1, "void": 0},
                {"item": "B", "quantity": 1, "void": 1}, {"item": "B", "quantity": 2, "void": 0}, {"item": "", "quantity": 1}]
        self.assertEqual(pst.cart_lines(tags), [("A", 1), ("B", 3)])

    def test_the_receipt_is_at_no_value_into_the_room_naming_the_cart(self):
        r = pst.receipt("Co", "Room", "PST-C-1", [("A", 2)], {"A": "Nos"})
        self.assertEqual((r["purpose"], r["stock_entry_type"], r["pp_pst_cart"], r["docstatus"]), ("Material Receipt",) * 2 + ("PST-C-1", 1))
        (line,) = r["items"]
        self.assertEqual(line, {"item_code": "A", "qty": 2, "uom": "Nos", "stock_uom": "Nos", "conversion_factor": 1,
                                "t_warehouse": "Room", "basic_rate": 0, "allow_zero_valuation_rate": 1})

    def test_the_transfer_moves_the_same_lines_from_the_room(self):
        t = pst.transfer("Co", "Room", "Store", "PST-C-1", [("A", 2)], {"A": "Nos"})
        self.assertEqual((t["purpose"], t["from_warehouse"], t["to_warehouse"], t["pp_pst_cart"]), ("Material Transfer", "Room", "Store", "PST-C-1"))
        self.assertEqual((t["items"][0]["s_warehouse"], t["items"][0]["t_warehouse"], t["items"][0]["qty"]), ("Room", "Store", 2))

    def test_a_cart_is_done_when_sent_or_kept_in_the_room(self):
        self.assertTrue(pst.finished({"state": "Sent", "destination": "S"}, "R"))
        self.assertTrue(pst.finished({"state": "Received", "destination": "R"}, "R"))
        self.assertFalse(pst.finished({"state": "Received", "destination": "S"}, "R"))
        self.assertFalse(pst.finished({"state": "Open", "destination": "R"}, "R"))


class Report(unittest.TestCase):
    def test_worker_rows_pieces_hours_and_per_hour(self):
        g = [{"tagged_on": "2026-11-27", "station": "S1", "worker": "Ana", "hour": 9, "pieces": 40},
             {"tagged_on": "2026-11-27", "station": "S1", "worker": "Ana", "hour": 10, "pieces": 35},
             {"tagged_on": "2026-11-27", "station": "S1", "worker": "Ben", "hour": 10, "pieces": 7},
             {"tagged_on": "2026-11-28", "station": "S1", "worker": "Ana", "hour": 9, "pieces": 0}]
        self.assertEqual(pst.worker_rows(g), [
            {"day": "2026-11-27", "station": "S1", "worker": "Ana", "pieces": 75, "hours": 2, "per_hour": 37.5},
            {"day": "2026-11-27", "station": "S1", "worker": "Ben", "pieces": 7, "hours": 1, "per_hour": 7.0}])

    def test_colour_rows_and_sell_through(self):
        rows = pst.colour_rows([("Blue", D(2026, 11, 2)), ("Green", D(2026, 11, 9))],
                               {("Blue", "2026-11-02"): 40}, {("Blue", "2026-11-02"): 10.0, ("Green", "2026-11-09"): 3.0})
        self.assertEqual(rows, [{"colour": "Blue", "week_start": "2026-11-02", "tagged": 40, "sold": 10.0, "sell_through": 25.0},
                                {"colour": "Green", "week_start": "2026-11-09", "tagged": 0, "sold": 3.0, "sell_through": 0.0}])

    def test_the_summary_says_the_whole_count(self):
        s = pst.summary_of([{"pieces": 75, "worker": "Ana"}, {"pieces": 7, "worker": "Ben"}],
                           [{"tagged": 40, "sold": 10.0}], D(2026, 11, 27), D(2026, 11, 27))
        self.assertEqual(s, "2026-11-27 to 2026-11-27: 82 pieces tagged by 2 workers. Colour weeks: 40 tagged, 10 sold.")


class Links(unittest.TestCase):
    def test_a_link_reads_back_only_with_the_retailers_secret(self):
        link = pst.link_of("https://p.example", "shop.example.com", "PST-S-00001", 3, b"k")
        token = link.split("&t=")[1]
        self.assertEqual(pst.code_of("shop.example.com", token, [b"x", b"k"]), ("PST-S-00001", 3))
        self.assertIsNone(pst.code_of("shop.example.com", token, [b"x"]))
        self.assertIsNone(pst.code_of("other.example.com", token, [b"k"]))
        self.assertIsNone(pst.code_of("shop.example.com", token.replace(".3.", ".0."), [b"k"]))

    def test_a_link_is_made_for_its_settings(self):
        self.assertNotEqual(pst.made_for({"settings": "A"}), pst.made_for({"settings": "B"}))

    def test_a_press_names_its_records_and_a_stale_press_is_refused(self):
        body = {"point": "desk_action/1", "context": {"v": 1, "records": [{"doctype": "PP PST Report", "name": "R1"}]}}
        self.assertEqual(pst.records_of(body, "PP PST Report", 1), ["R1"])
        with self.assertRaises(ValueError):
            pst.records_of(dict(body, context=dict(body["context"], records=[{"doctype": "X", "name": "R1"}])), "PP PST Report")
        self.assertIn("too far", pst.verify("100", "x", b"{}", "s", now=1000))
        self.assertIn("too far", pst.verify("9" * 40, "x", b"{}", "s", now=1000))

    def test_every_answer_fits_the_extension_points_words(self):
        self.assertEqual(len(pst.message("x " * 300)["message"]["body"]), 280)

    def test_the_library_prefix_names_the_fields_too(self):
        try:
            pst.use_prefix("IVENDNEXT PST")
            self.assertEqual((pst.dt("Tag"), pst.FIELD_COLOUR, pst.FIELD_CART),
                             ("IVENDNEXT PST Tag", "ivendnext_pst_tag_colour", "ivendnext_pst_cart"))
        finally:
            pst.use_prefix("PP PST")


if __name__ == "__main__":
    unittest.main()
