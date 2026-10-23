"""S45's core rules (``backoffice.py``): a dish's recipe opened into the stock it uses, the day's sales grouped into one
issue per store and day, the day parts, the short parts named, the food cost and the allergen check.

    python3 -m unittest discover -s samples/s45_restaurant_back_office/tests -p 'test_*.py'
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import backoffice as bo  # noqa: E402

ITEMS = {
    "BUN": {"is_stock_item": 1}, "PATTY": {"is_stock_item": 1}, "MAYO": {"is_stock_item": 1},
    "MUSTARD": {"is_stock_item": 1}, "BEANS": {"is_stock_item": 1}, "MILK": {"is_stock_item": 1},
    "FRIES": {"is_stock_item": 1}, "SODA": {"is_stock_item": 1}, "WATER": {"is_stock_item": 0},
    "SAUCE": {"is_stock_item": 0, "default_bom": "BOM-SAUCE"},
    "BURGER": {"is_stock_item": 0, "default_bom": "BOM-BURGER"},
    "COFFEE": {"is_stock_item": 0, "default_bom": "BOM-COFFEE"},
    "COMBO": {"is_stock_item": 0, "default_bom": "BOM-COMBO"},
    "SALAD": {"is_stock_item": 0},
    "BATCH-DOUGH": {"is_stock_item": 0, "default_bom": "BOM-DOUGH"},
}
BOMS = {
    "BOM-SAUCE": {"quantity": 10, "items": [{"item_code": "MAYO", "stock_qty": 0.2}, {"item_code": "MUSTARD", "stock_qty": 0.05}]},
    "BOM-BURGER": {"quantity": 1, "items": [{"item_code": "BUN", "stock_qty": 1}, {"item_code": "PATTY", "stock_qty": 1},
                                            {"item_code": "SAUCE", "stock_qty": 1, "bom_no": "BOM-SAUCE"}]},
    "BOM-COFFEE": {"quantity": 1, "items": [{"item_code": "BEANS", "stock_qty": 0.018}, {"item_code": "MILK", "stock_qty": 0.15},
                                            {"item_code": "WATER", "stock_qty": 0.2}]},
    "BOM-COMBO": {"quantity": 1, "items": [{"item_code": "BURGER", "stock_qty": 1}, {"item_code": "FRIES", "stock_qty": 0.15},
                                           {"item_code": "SODA", "stock_qty": 1}]},
    "BOM-DOUGH": {"quantity": 1, "items": [{"item_code": "BATCH-DOUGH", "stock_qty": 1}]},
}
PARTS = [{"day_part": "Breakfast", "from_time": "06:00:00", "to_time": "11:00:00"},
         {"day_part": "Lunch", "from_time": "11:00:00", "to_time": "16:00:00"},
         {"day_part": "Late", "from_time": "22:00:00", "to_time": "02:00:00"}]


class Recipes(unittest.TestCase):
    def test_r1_a_dish_takes_its_recipes_parts_per_unit_made(self):
        got, notes = bo.parts_of("BURGER", 2, ITEMS, BOMS)
        self.assertEqual({k: round(v, 6) for k, v in got.items()},
                         {"BUN": 2, "PATTY": 2, "MAYO": 0.04, "MUSTARD": 0.01})     # the sauce's recipe makes 10
        self.assertEqual(notes, [])

    def test_r2_a_dish_inside_a_dish_is_opened_too(self):
        got, _ = bo.parts_of("COMBO", 1, ITEMS, BOMS)
        self.assertEqual({k: round(v, 6) for k, v in got.items()},
                         {"BUN": 1, "PATTY": 1, "MAYO": 0.02, "MUSTARD": 0.005, "FRIES": 0.15, "SODA": 1})

    def test_r3_a_part_not_stocked_with_no_recipe_is_skipped_and_named(self):
        got, notes = bo.parts_of("COFFEE", 1, ITEMS, BOMS)
        self.assertNotIn("WATER", got)
        self.assertEqual(notes, ["WATER: no recipe"])

    def test_r4_a_stock_item_sold_is_never_opened(self):
        self.assertEqual(bo.parts_of("SODA", 3, ITEMS, BOMS), ({"SODA": 3}, []))

    def test_r5_a_recipe_that_goes_round_is_refused(self):
        with self.assertRaises(bo.RecipeError):
            bo.parts_of("BATCH-DOUGH", 1, ITEMS, BOMS)

    def test_r6_an_inactive_recipe_takes_nothing_and_says_so(self):
        boms = dict(BOMS, **{"BOM-COFFEE": {"quantity": 0, "items": []}})
        self.assertEqual(bo.parts_of("COFFEE", 1, ITEMS, boms), ({}, ["COFFEE: recipe BOM-COFFEE is not active"]))

    def test_r7_the_recipes_to_read_reach_every_level(self):
        self.assertEqual(bo.boms_to_read(["COMBO", "SODA", "SALAD"], ITEMS), ["BOM-COMBO"])
        self.assertEqual(bo.bom_rows_to_read({"BOM-COMBO": BOMS["BOM-COMBO"]}, ITEMS), ["BOM-BURGER"])


SALES = [{"name": "S1", "posting_date": "2026-10-23", "posting_time": "08:15:00", "owner": "ana@x", "set_warehouse": "Store A",
          "pos_profile": "A"},
         {"name": "S2", "posting_date": "2026-10-23", "posting_time": "12:40:10.5", "owner": "ben@x", "pos_profile": "B"},
         {"name": "S3", "posting_date": "2026-10-23", "posting_time": "23:30:00", "owner": "ana@x", "set_warehouse": "Store A",
          "pos_profile": "A"},
         {"name": "S4", "posting_date": "2026-10-24", "posting_time": "09:00:00", "owner": "ana@x", "set_warehouse": "Store A",
          "pos_profile": "A"},
         {"name": "R1", "posting_date": "2026-10-23", "posting_time": "13:00:00", "owner": "ben@x", "set_warehouse": "Store A",
          "pos_profile": "A", "is_return": 1}]
LINES = [{"parent": "S1", "item_code": "BURGER", "qty": 2, "stock_qty": 2, "net_amount": 163.64},
         {"parent": "S1", "item_code": "SODA", "qty": 1, "stock_qty": 1, "net_amount": 18.18},
         {"parent": "S2", "item_code": "COFFEE", "qty": 1, "stock_qty": 1, "net_amount": 27.27},
         {"parent": "S3", "item_code": "COMBO", "qty": 1, "stock_qty": 1, "net_amount": 118.18, "warehouse": "Store A"},
         {"parent": "S4", "item_code": "SALAD", "qty": 1, "stock_qty": 1, "net_amount": 31.82},
         {"parent": "R1", "item_code": "BURGER", "qty": -1, "stock_qty": -1, "net_amount": -81.82},
         {"parent": "GONE", "item_code": "BURGER", "qty": 1, "stock_qty": 1, "net_amount": 1}]


class Groups(unittest.TestCase):
    def setUp(self):
        self.g = bo.group_lines(SALES, LINES, ITEMS, {"B": "Store B"}, PARTS)

    def test_g1_one_issue_per_store_and_day(self):
        self.assertEqual(sorted(self.g), [("Store A", "2026-10-23"), ("Store A", "2026-10-24"), ("Store B", "2026-10-23")])
        self.assertEqual(self.g[("Store A", "2026-10-23")]["sales"], ["S1", "S3", "R1"])

    def test_g2_a_sale_with_no_store_takes_its_tills(self):
        self.assertEqual(self.g[("Store B", "2026-10-23")]["sales"], ["S2"])

    def test_g3_the_issue_is_dated_at_the_days_last_sale(self):
        self.assertEqual(self.g[("Store A", "2026-10-23")]["posting_time"], "23:30:00")
        self.assertEqual(self.g[("Store B", "2026-10-23")]["posting_time"], "12:40:10")

    def test_g4_each_line_carries_the_report_and_its_day_part(self):
        rows = {(r["sale"], r["item_code"]): r for r in self.g[("Store A", "2026-10-23")]["lines"]}
        self.assertEqual(rows[("S1", "BURGER")], {"sale": "S1", "item_code": "BURGER", "qty": 2, "amount": 163.64,
                                                  "server": "ana@x", "sold_at": "08:15:00", "day_part": "Breakfast",
                                                  "has_recipe": 1})
        self.assertEqual(rows[("S3", "COMBO")]["day_part"], "Late")         # a part that runs past midnight
        self.assertEqual(rows[("S1", "SODA")]["has_recipe"], 0)

    def test_g5_a_kitchen_store_issues_for_every_store(self):
        g = bo.group_lines(SALES, LINES, ITEMS, {"B": "Store B"}, PARTS, kitchen="Kitchen")
        self.assertEqual({v["issue_from"] for v in g.values()}, {"Kitchen"})
        self.assertEqual({v["store"] for v in g.values()}, {"Store A", "Store B"})

    def test_g6_a_return_takes_nothing_back_and_a_stock_item_is_not_issued(self):
        need, _ = bo.need_of(self.g[("Store A", "2026-10-23")], ITEMS, BOMS)
        self.assertEqual({k: round(v, 6) for k, v in need.items()},
                         {"BUN": 3, "PATTY": 3, "MAYO": 0.06, "MUSTARD": 0.015, "FRIES": 0.15, "SODA": 1})

    def test_g7_a_day_with_no_recipe_issues_nothing(self):
        self.assertEqual(bo.need_of(self.g[("Store A", "2026-10-24")], ITEMS, BOMS), ({}, []))

    def test_g7b_a_time_the_shop_prints_without_its_leading_zero(self):
        self.assertEqual(bo.clock_of("11:35:9.97032"), "11:35:09")
        self.assertEqual(bo.clock_of("9:5:0"), "09:05:00")
        self.assertTrue(bo.booked_from({"posting_date": "2026-10-23", "posting_time": "11:35:9.97"}, "2026-10-23 11:34:50"))
        self.assertFalse(bo.booked_from({"posting_date": "2026-10-23", "posting_time": "11:34:9.5"}, "2026-10-23 11:34:50"))
        self.assertEqual(bo.moment_of("2026-10-23 11:34:5"), "2026-10-23 11:34:05")
        g = bo.group_lines([dict(SALES[0], posting_time="23:59:7.5")], LINES[:1], ITEMS, {}, PARTS)
        self.assertEqual(next(iter(g.values()))["posting_time"], "23:59:07")

    def test_g8_day_parts(self):
        self.assertEqual(bo.day_part_of("10:59:59", PARTS), "Breakfast")
        self.assertEqual(bo.day_part_of("11:00:00", PARTS), "Lunch")
        self.assertEqual(bo.day_part_of("01:30:00", PARTS), "Late")
        self.assertEqual(bo.day_part_of("18:00:00", PARTS), "")
        self.assertEqual(bo.day_part_of("bad", PARTS), "")


class Records(unittest.TestCase):
    def test_d1_the_issue_names_its_sales_and_holds_its_parts(self):
        g = bo.group_lines(SALES, LINES, ITEMS, {"B": "Store B"}, PARTS)[("Store A", "2026-10-23")]
        need, notes = bo.need_of(g, ITEMS, BOMS)
        d = bo.issue_doc("Co", g, need, {"BUN": {"stock_uom": "Nos"}}, notes)
        self.assertEqual((d["status"], d["sales"], d["sale_count"], d["food_sales"]), ("Pending", "S1\nS3\nR1", 3, 218.18))
        self.assertEqual(d["parts"][0], {"item_code": "BUN", "qty": 3, "uom": "Nos"})
        self.assertEqual(bo.issue_doc("Co", dict(g, lines=[]), {}, {}, [])["status"], "Nothing to issue")

    def test_d2_the_stock_entry_is_the_shops_own_material_issue_submitted_in_one_call(self):
        issue = {"name": "RBO-ISS-00001", "issue_from": "Kitchen", "store": "Store A", "posting_date": "2026-10-23",
                 "posting_time": "23:30:00", "sale_count": 3, "parts": [{"item_code": "BUN", "qty": 3, "uom": "Nos"}]}
        se = bo.stock_entry("Co", issue)
        self.assertEqual((se["purpose"], se["stock_entry_type"], se["docstatus"], se["set_posting_time"]),
                         ("Material Issue", "Material Issue", 1, 1))
        self.assertEqual((se["posting_date"], se["posting_time"], se["pp_rbo_issue"]), ("2026-10-23", "23:30:00", "RBO-ISS-00001"))
        self.assertEqual(se["items"], [{"item_code": "BUN", "qty": 3, "s_warehouse": "Kitchen", "uom": "Nos",
                                        "stock_uom": "Nos", "conversion_factor": 1}])
        self.assertNotIn("expense_account", se["items"][0])     # the shop's own account for an issue, never the app's

    def test_d3_every_short_part_is_named(self):
        parts = [{"item_code": "BUN", "qty": 3}, {"item_code": "BEANS", "qty": 0.9}, {"item_code": "MILK", "qty": 2}]
        short = bo.short_of(parts, {"BUN": 3, "BEANS": 0.5})
        self.assertEqual(short, [("BEANS", 0.9, 0.5), ("MILK", 2.0, 0.0)])
        self.assertIn("BEANS (needs 0.9, has 0.5), MILK (needs 2, has 0)", bo.short_note(short, "Kitchen"))


class FoodCost(unittest.TestCase):
    def test_f1_theoretical_against_actual(self):
        ledger = [
            {"item_code": "BUN", "actual_qty": -10, "stock_value_difference": -40, "voucher_type": "Stock Entry", "voucher_no": "OURS-1"},
            {"item_code": "BUN", "actual_qty": -2, "stock_value_difference": -8, "voucher_type": "Stock Entry", "voucher_no": "WASTE-1"},
            {"item_code": "BUN", "actual_qty": 50, "stock_value_difference": 200, "voucher_type": "Stock Entry", "voucher_no": "RECV-1"},
            {"item_code": "SODA", "actual_qty": -6, "stock_value_difference": -42, "voucher_type": "Sales Invoice", "voucher_no": "SI-1"},
            {"item_code": "SODA", "actual_qty": 1, "stock_value_difference": 7, "voucher_type": "Sales Invoice", "voucher_no": "SI-2"},
            {"item_code": "BUN", "actual_qty": 0, "stock_value_difference": -12, "voucher_type": "Stock Reconciliation", "voucher_no": "SR-1"},
            {"item_code": "BUN", "actual_qty": -5, "stock_value_difference": -20, "voucher_type": "Stock Entry", "voucher_no": "MOVE-1"}]
        counts = [{"item_code": "BUN", "qty": 30, "current_qty": 33, "amount_difference": -12}]
        got = bo.food_cost(ledger, {"OURS-1"}, {"WASTE-1"}, counts, 500, {"BUN": "Nos"})
        bun, soda = got["lines"]
        self.assertEqual((bun["recipe_qty"], bun["other_qty"], bun["count_qty"], bun["sold_qty"], bun["actual_qty"]),
                         (10, 2, 3, 0, 15))          # receipts and transfers are not use; the count's ledger row is the count
        self.assertEqual((bun["theoretical_value"], bun["actual_value"], bun["variance_value"]), (40, 60, 20))
        self.assertEqual((soda["sold_qty"], soda["theoretical_value"]), (5, 35))     # a return counts back
        self.assertEqual((got["theoretical_cost"], got["actual_cost"], got["theoretical_pct"], got["actual_pct"]),
                         (75, 95, 15, 19))

    def test_f2_no_sales_no_percent(self):
        self.assertEqual(bo.food_cost([], set(), set(), [], 0, {})["actual_pct"], 0)


class Allergens(unittest.TestCase):
    WORDS = {"BUN": "Cereals containing gluten, Sesame", "MAYO": "Eggs", "MUSTARD": "Mustard", "MILK": "Milk",
             "BURGER": "Contains: Cereals containing gluten; Eggs", "COFFEE": "Milk", "COMBO": ""}

    def test_a1_a_dish_missing_an_allergen_of_its_recipe_at_any_depth(self):
        self.assertEqual(bo.allergens_missing("BURGER", ITEMS, BOMS, self.WORDS), (["Sesame", "Mustard"], ["BUN", "MUSTARD"]))

    def test_a2_a_dish_naming_them_all_passes(self):
        self.assertEqual(bo.allergens_missing("COFFEE", ITEMS, BOMS, self.WORDS), ([], []))

    def test_a3_a_dish_inside_a_dish_carries_its_allergens(self):
        missing, _ = bo.allergens_missing("COMBO", ITEMS, BOMS, self.WORDS)
        self.assertEqual(sorted(w.lower() for w in missing), ["cereals containing gluten", "eggs", "mustard", "sesame"])

    def test_a4_words_as_the_shop_writes_them(self):
        self.assertEqual(bo.words_of("Contains: Milk; eggs\nSesame, milk"), ["Milk", "eggs", "Sesame"])
        self.assertEqual(bo.unknown_words("Milk, Diary", bo.EU_14), ["Diary"])
        self.assertEqual(bo.unknown_words("Diary", []), [])


class Calls(unittest.TestCase):
    def test_c1_a_press_names_its_records(self):
        body = {"point": "desk_action/1", "context": {"v": 1, "records": [{"doctype": "Item", "name": "A"},
                                                                          {"doctype": "Item", "name": "A"}]}}
        self.assertEqual(bo.records_of(body, "Item"), ["A"])
        with self.assertRaises(ValueError):
            bo.records_of(body, "PP RBO Settings", most=1)
        with self.assertRaises(ValueError):
            bo.records_of({"point": "x"}, "Item")

    def test_c3_a_long_body_is_cut(self):
        out = bo.message("T", "x" * 400)
        self.assertEqual((len(out["message"]["body"]), out["message"]["body"][-1]), (280, "…"))

    def test_c2_the_library_prefix(self):
        bo.use_prefix("IVENDNEXT RBO")
        try:
            self.assertEqual((bo.dt("Issue"), bo.FIELD), ("IVENDNEXT RBO Issue", "ivendnext_rbo"))
        finally:
            bo.use_prefix("PP RBO")


if __name__ == "__main__":
    unittest.main()
