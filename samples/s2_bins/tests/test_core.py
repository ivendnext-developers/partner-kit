"""S2 core tests — stdlib only, no bench:  python3 -m unittest discover -s samples/s2_bins/tests -p 'test_core.py' -v"""

import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import core  # noqa: E402

ROWS = [
    {"name": "SF-01--A", "item": "A", "bin": "SF-01", "qty": 5, "kind": "Shop floor"},
    {"name": "SF-02--A", "item": "A", "bin": "SF-02", "qty": 2, "kind": "Shop floor"},
    {"name": "BR-01--B", "item": "B", "bin": "BR-01", "qty": 8, "kind": "Back room"},
    {"name": "SF-03--C", "item": "C", "bin": "SF-03", "qty": 0, "kind": "Shop floor"},
]


def ctx(*codes):
    return {"lines": [{"item_code": c, "qty": 1, "uom": "Nos", "luid": str(i)} for i, c in enumerate(codes)]}


class WhereAnswer(unittest.TestCase):
    def test_shop_floor_first_with_the_fullest_bin(self):
        m = core.where_answer(ctx("A"), ROWS)["message"]
        self.assertEqual((m["title"], m["level"]), ("Where is it?", "success"))
        self.assertIn("A: shop floor SF-01 (5) (+1 more bin)", m["body"])

    def test_back_room_when_the_floor_has_none(self):
        m = core.where_answer(ctx("B"), ROWS)["message"]
        self.assertEqual(m["level"], "info")
        self.assertIn("B: back room BR-01 (8), fetch it", m["body"])

    def test_no_bin_and_an_empty_bin_both_warn(self):
        m = core.where_answer(ctx("A", "C", "Z"), ROWS)["message"]
        self.assertEqual(m["level"], "warning")
        self.assertIn("C: no bin recorded", m["body"])
        self.assertIn("Z: no bin recorded", m["body"])

    def test_empty_sale_and_the_cap(self):
        self.assertEqual(core.where_answer(ctx(), ROWS)["message"]["level"], "info")
        many = ctx(*[f"ITEM-{i:03d}-WITH-A-LONG-CODE" for i in range(80)])
        body = core.where_answer(many, ROWS)["message"]["body"]
        self.assertLessEqual(len(body), 280)
        self.assertIn("more", body)


class SaleDecrements(unittest.TestCase):
    def test_takes_from_the_fullest_shop_floor_bin_then_the_next(self):
        plan = core.sale_decrements("SINV-1", [{"item_code": "A", "qty": 6}], ROWS)
        self.assertEqual(plan, [{"name": "SF-01--A", "take": 5.0, "short": 0.0},
                                {"name": "SF-02--A", "take": 1.0, "short": 0.0}])

    def test_never_below_zero_the_rest_is_short(self):
        plan = core.sale_decrements("SINV-1", [{"item_code": "A", "qty": 9}], ROWS)
        self.assertEqual(plan[-1], {"name": "SF-02--A", "take": 2.0, "short": 2.0})

    def test_back_room_stock_is_never_decremented_by_a_sale(self):
        self.assertEqual(core.sale_decrements("SINV-1", [{"item_code": "B", "qty": 1}], ROWS), [])

    def test_the_same_sale_twice_takes_nothing_more(self):
        rows = [dict(r) for r in ROWS]
        rows[0]["movements"] = [{"kind": "Sale", "qty": 2, "reference": "SINV-1"}]
        rows[0]["qty"] = 3
        self.assertEqual(core.sale_decrements("SINV-1", [{"item_code": "A", "qty": 2}], rows), [])

    def test_a_half_written_split_take_finishes_on_retry(self):
        rows = [dict(r) for r in ROWS]
        rows[0]["movements"] = [{"kind": "Sale", "qty": 5, "reference": "SINV-1"}]
        rows[0]["qty"] = 0
        plan = core.sale_decrements("SINV-1", [{"item_code": "A", "qty": 6}], rows)
        self.assertEqual(plan, [{"name": "SF-02--A", "take": 1.0, "short": 0.0}])


    def test_a_recorded_shortfall_is_not_taken_later_from_a_refilled_bin(self):
        # sold 5 when the floor held 3: took 3, short 2 — then a pick fills a second floor bin
        rows = [{"name": "SF-01--A", "item": "A", "bin": "SF-01", "qty": 0, "kind": "Shop floor",
                 "movements": [{"kind": "Sale", "qty": 3, "short": 2, "reference": "SINV-9"}]},
                {"name": "SF-09--A", "item": "A", "bin": "SF-09", "qty": 6, "kind": "Shop floor", "movements": []}]
        self.assertEqual(core.sale_decrements("SINV-9", [{"item_code": "A", "qty": 5}], rows), [])


class NoFramework(unittest.TestCase):
    def test_core_imports_no_framework(self):
        src = (HERE.parent / "core.py").read_text()
        for name in ("frappe", "erpnext", "ivendnext", "requests"):
            self.assertNotIn(f"import {name}", src)
            self.assertNotIn(f"from {name}", src)


if __name__ == "__main__":
    unittest.main()
