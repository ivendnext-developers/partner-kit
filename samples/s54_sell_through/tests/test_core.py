"""S54's pure core: a press, a run, an attribute's order, the group's variants, the two reports' answers read by their
column names, the rows side by side in the retailer's order, the sell-through and the summary.

    python3 -m unittest discover -s samples/s54_sell_through/tests -p 'test_*.py'
"""

import datetime
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sst  # noqa: E402

TODAY = datetime.date(2026, 10, 29)


def run_doc(**k):
    d = {"name": "SST-00001", "title": "Summer dresses", "item_group": "Dresses", "style": "",
         "sold_since": "2026-10-01", "size_attribute": "Size", "colour_attribute": "Colour",
         "stores": [{"store": "Mall - DR"}, {"store": "High Street - DR"}]}
    d.update(k)
    return d


def a_run(**k):
    r = sst.run_of(run_doc(**k), TODAY)
    assert isinstance(r, sst.Run), r
    return r


def item_rows():
    """As the record API answers ``attributes.attribute`` and ``attributes.attribute_value``: one row per attribute."""
    out = []
    for style, colours in (("DRESS-A", ("Red", "Blue")), ("DRESS-B", ("Black",))):
        for c in colours:
            for s in ("S", "M", "L"):
                code = f"{style}-{c[:3].upper()}-{s}"
                out += [{"name": code, "variant_of": style, "attribute": "Colour", "attribute_value": c},
                        {"name": code, "variant_of": style, "attribute": "Size", "attribute_value": s}]
    out.append({"name": "SCARF", "variant_of": None, "attribute": None, "attribute_value": None})   # not a variant
    out.append({"name": "DRESS-A-GRN", "variant_of": "DRESS-A", "attribute": "Colour", "attribute_value": "Green"})  # no size
    return out


SIZE = {"attribute_name": "Size", "item_attribute_values": [
    {"attribute_value": "L", "idx": 3}, {"attribute_value": "S", "idx": 1}, {"attribute_value": "M", "idx": 2}]}
COLOUR = {"attribute_name": "Colour", "item_attribute_values": [
    {"attribute_value": "Red", "idx": 1}, {"attribute_value": "Blue", "idx": 2}, {"attribute_value": "Black", "idx": 3}]}


class Press(unittest.TestCase):
    def body(self, records):
        return {"point": "desk_action/1", "context": {"v": 1, "user": "buyer@x", "records": records}}

    def test_one_run_a_press(self):
        self.assertEqual(sst.run_of_press(self.body([{"doctype": sst.RUN, "name": "SST-00001"}])), ("SST-00001", "buyer@x"))
        for bad in ([], [{"doctype": sst.RUN, "name": "A"}, {"doctype": sst.RUN, "name": "B"}],
                    [{"doctype": "Item", "name": "A"}], [{"doctype": sst.RUN, "name": ""}]):
            with self.assertRaises(ValueError):
                sst.run_of_press(self.body(bad))
        with self.assertRaises(ValueError):
            sst.run_of_press({"point": "check/1", "context": {}})


class RunOf(unittest.TestCase):
    def test_a_run_as_the_service_reads_it(self):
        r = a_run()
        self.assertEqual((r.item_group, r.style, r.since, r.size_attribute, r.colour_attribute, r.stores),
                         ("Dresses", "", datetime.date(2026, 10, 1), "Size", "Colour",
                          ["Mall - DR", "High Street - DR"]))

    def test_each_misfilled_run_says_what_to_fix(self):
        for k, words in ((dict(item_group=""), "fill the item group and the size attribute"),
                         (dict(sold_since=""), "fill Sold since"),
                         (dict(sold_since="2026-10-31"), "after today"),
                         (dict(sold_since="2024-10-01"), "two years"),
                         (dict(colour_attribute="Size"), "must differ"),
                         (dict(stores=[]), "at least one store"),
                         (dict(stores=[{"store": f"S{i}"} for i in range(21)]), "at most 20 stores")):
            r = sst.run_of(run_doc(**k), TODAY)
            self.assertIsInstance(r, str, k)
            self.assertIn(words, r)

    def test_a_store_twice_or_blank_counts_once(self):
        self.assertEqual(a_run(stores=[{"store": "A"}, {"store": "A"}, {"store": ""}, {}]).stores, ["A"])


class Attributes(unittest.TestCase):
    def test_an_attributes_own_order(self):
        self.assertEqual(sst.order_of(SIZE), {"S": 0, "M": 1, "L": 2})
        self.assertEqual(sst.order_of({}), {})

    def test_the_groups_variants_with_their_size_and_colour(self):
        v = sst.variants_of(item_rows(), a_run())
        self.assertEqual(len(v), 9)                                   # SCARF and the sizeless green are left out
        self.assertEqual(v["DRESS-A-RED-M"], {"style": "DRESS-A", "size": "M", "colour": "Red"})

    def test_a_named_style_keeps_its_own_variants_only(self):
        self.assertEqual({x["style"] for x in sst.variants_of(item_rows(), a_run(style="DRESS-B")).values()}, {"DRESS-B"})

    def test_no_colour_attribute_counts_a_sizes_colours_together(self):
        v = sst.variants_of(item_rows(), a_run(colour_attribute=""))
        self.assertEqual({x["colour"] for x in v.values()}, {""})


class Reports(unittest.TestCase):
    def setUp(self):
        self.items = sst.variants_of(item_rows(), a_run())

    def test_pos_sale_report_by_its_column_names_as_lists_or_dicts(self):
        cols = ["store", "pos", "item", "item_name", "sales", "refund", "discount", "net_sales", "unit_solds"]
        lists = {"message": {"columns": cols, "result": [["Mall - DR", "P", "DRESS-A-RED-M", "x", 90, -30, 0, 60, 2],
                                                         ["Mall - DR", "P", "SCARF", "x", 10, 0, 0, 10, 1]]}}
        self.assertEqual(sst.sold_of(lists, self.items), {"DRESS-A-RED-M": 2.0})
        dicts = {"message": {"columns": [{"fieldname": c} for c in cols],
                             "result": [{"item": "DRESS-A-RED-M", "unit_solds": "3"}]}}
        self.assertEqual(sst.sold_of(dicts, self.items), {"DRESS-A-RED-M": 3.0})

    def test_a_sale_report_without_its_columns_is_refused(self):
        with self.assertRaises(ValueError):
            sst.sold_of({"message": {"columns": ["a", "b"], "result": [[1, 2]]}}, self.items)
        with self.assertRaises(ValueError) as e:
            sst.sold_of({"message": {"prepared_report": True, "doc": None}}, self.items)
        self.assertIn("POS Sale Report was made a prepared report", str(e.exception))
        self.assertIn("untick Prepared Report", str(e.exception))
        with self.assertRaises(ValueError) as e:
            sst.stock_of({"message": {"prepared_report": True, "doc": None, "result": []}}, self.items, "Mall - DR")
        self.assertIn("Stock Projected Quantity was made a prepared report", str(e.exception))
        with self.assertRaises(ValueError) as e:
            sst.sold_of({"message": {"columns": []}}, self.items)
        self.assertIn("POS Sale Report answered no rows", str(e.exception))
        self.assertEqual(sst.sold_of({"message": {"columns": [], "result": []}}, self.items), {})

    def test_stock_less_the_tills_open_days(self):
        cols = [{"fieldname": f} for f in ("item_code", "item_name", "warehouse", "actual_qty", "reserved_qty_for_pos",
                                            "projected_qty")]
        a = {"message": {"columns": cols, "result": [["DRESS-A-RED-M", "x", "Mall - DR", 5, 2, 3],
                                                     ["DRESS-A-RED-L", "x", "Mall - DR - Back", 9, 0, 9],
                                                     ["SCARF", "x", "Mall - DR", 7, 0, 7]]}}
        self.assertEqual(sst.stock_of(a, self.items, "Mall - DR"), {"DRESS-A-RED-M": 3.0})
        with self.assertRaises(ValueError):
            sst.stock_of({"message": {"columns": ["x"], "result": [[1]]}}, self.items, "Mall - DR")


class Rows(unittest.TestCase):
    def test_sell_through(self):
        self.assertEqual(sst.sell_through(3, 1), 75.0)
        self.assertEqual(sst.sell_through(1, 2), 33.3)
        self.assertEqual(sst.sell_through(2, 0), 100.0)
        self.assertEqual(sst.sell_through(2, -1), 100.0)              # negative stock is counted as none
        self.assertEqual((sst.sell_through(0, 5), sst.sell_through(-1, 5)), (0.0, 0.0))

    def test_rows_side_by_side_in_the_retailers_order(self):
        run = a_run()
        items = sst.variants_of(item_rows(), run)
        sold = {"Mall - DR": {"DRESS-A-RED-L": 1, "DRESS-A-RED-S": 3, "DRESS-A-BLU-M": 2},
                "High Street - DR": {"DRESS-A-RED-S": 1}}
        stock = {"Mall - DR": {"DRESS-A-RED-S": 0, "DRESS-A-RED-L": 4, "DRESS-B-BLA-M": 6},
                 "High Street - DR": {"DRESS-A-RED-S": 2}}
        rows = sst.rows_of(items, sold, stock, run, sst.order_of(SIZE), sst.order_of(COLOUR))
        self.assertEqual([(r["style"], r["colour"], r["size"], r["store"]) for r in rows],
                         [("DRESS-A", "Red", "S", "Mall - DR"), ("DRESS-A", "Red", "S", "High Street - DR"),
                          ("DRESS-A", "Red", "L", "Mall - DR"), ("DRESS-A", "Blue", "M", "Mall - DR"),
                          ("DRESS-B", "Black", "M", "Mall - DR")])
        first = rows[0]
        self.assertEqual((first["sold"], first["in_stock"], first["sell_through"], first["none_left"], first["item"]),
                         (3, 0, 100.0, 1, "DRESS-A-RED-S"))
        self.assertEqual((rows[2]["sell_through"], rows[2]["none_left"]), (20.0, 0))
        self.assertEqual((rows[4]["sold"], rows[4]["sell_through"]), (0, 0.0))     # held, not sold: still a row

    def test_without_colour_a_sizes_colours_are_one_row(self):
        run = a_run(colour_attribute="")
        items = sst.variants_of(item_rows(), run)
        rows = sst.rows_of(items, {"Mall - DR": {"DRESS-A-RED-M": 1, "DRESS-A-BLU-M": 2}}, {}, run, sst.order_of(SIZE), {})
        self.assertEqual([(r["style"], r["colour"], r["size"], r["sold"], r["item"]) for r in rows],
                         [("DRESS-A", "", "M", 3, "")])

    def test_number_sizes_without_a_list_go_by_number(self):
        run = a_run(colour_attribute="")
        items = {f"SHOE-{s}": {"style": "SHOE", "size": s, "colour": ""} for s in ("10", "6.5", "6", "11", "XL")}
        rows = sst.rows_of(items, {"Mall - DR": {k: 1 for k in items}}, {}, run, {}, {})
        self.assertEqual([r["size"] for r in rows], ["6", "6.5", "10", "11", "XL"])

    def test_the_summary(self):
        run = a_run()
        rows = [{"sold": 3, "in_stock": 0, "none_left": 1}, {"sold": 1, "in_stock": 4, "none_left": 0},
                {"sold": 0, "in_stock": -1, "none_left": 1}]
        self.assertEqual(sst.summary_of(rows, run),
                         "4 sold since 2026-10-01, 4 in stock now: 50.0% sold through, across 2 stores. "
                         "1 row sold out: none left in that store.")

    def test_every_answer_fits_the_extension_points_words(self):
        m = sst.message("x" * 400, "warning")["message"]
        self.assertLessEqual(len(m["body"]), 280)
        self.assertEqual((m["title"], m["level"]), ("Sell-through", "warning"))

    def test_the_library_prefix(self):
        try:
            sst.use_prefix("IVENDNEXT SST")
            self.assertEqual((sst.RUN, sst.STORE, sst.ROW),
                             ("IVENDNEXT SST Sell-through", "IVENDNEXT SST Store", "IVENDNEXT SST Row"))
        finally:
            sst.use_prefix("PP SST")


if __name__ == "__main__":
    unittest.main()
