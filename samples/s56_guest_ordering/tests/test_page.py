"""S56's guest page rules, run under node through ``tests/page_harness.js`` (a small stand-in for the browser): a dish's
sizes together under the dish, the picture or a plain tile, one price format, a running total, and the retailer's words in
``<bdi>`` with no guessed direction. Skipped where node is not installed."""

import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
NODE = shutil.which("node")

LATTE = {"code": "LATTE", "name": "Latte", "group": "Drinks", "price": 3.2, "image": "https://bistro.example.com/files/l.jpg",
         "groups": []}
COLD = [{"code": "COLD-L", "name": "Cold brew / Large", "group": "Drinks", "price": 4.5, "image": "", "groups": [],
         "family": "COLD", "base": "Cold brew", "size": "Large"},
        {"code": "COLD-R", "name": "Cold brew / Regular", "group": "Drinks", "price": 4.0, "image": "", "groups": [],
         "family": "COLD", "base": "Cold brew", "size": "Regular"}]
MENU = {"state": "open", "kind": "Table", "where": "طاولة 12", "currency": "USD", "most_lines": 10, "most_qty": 10,
        "menu": [{"group": "Drinks", "dishes": [COLD[0], COLD[1], LATTE,
                                                 {"code": "MOCHA", "name": "Mocha", "group": "Drinks", "price": None,
                                                  "image": "", "groups": []}]}]}


def page(**opts):
    out = subprocess.run([NODE, os.path.join(HERE, "page_harness.js"), json.dumps(opts)], capture_output=True, text=True,
                         timeout=60)
    if out.returncode:
        raise AssertionError(out.stderr)
    return json.loads(out.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class PageTest(unittest.TestCase):
    def test_p1_a_dishs_sizes_sit_together_with_a_picture_or_a_tile(self):
        p = page(answers={"/gor/menu": [MENU]})
        names = [d["name"] for d in p["dishes"]]
        self.assertEqual(names, ["Cold brew", "Latte", "Mocha"])                   # one card a dish, not a row a size
        cold = p["dishes"][0]
        self.assertEqual(len(cold["sizes"]), 2)
        self.assertTrue(cold["sizes"][0].startswith("Regular") and cold["sizes"][0].endswith("*"))   # the cheapest size is first and picked
        self.assertTrue(cold["sizes"][1].startswith("Large"))
        self.assertTrue(p["dishes"][1]["img"].endswith("/files/l.jpg"))
        self.assertTrue(cold["tile"] and p["dishes"][2]["tile"])                       # no picture: a plain tile

    def test_p2_one_price_format_in_the_stores_currency_without_a_country_tag(self):
        p = page(answers={"/gor/menu": [MENU]}, language="en-GB")
        self.assertEqual(p["dishes"][1]["price"], "$3.20")                            # never US$3.20
        self.assertEqual(p["dishes"][2]["price"], "")                                 # no price known: none shown

    def test_p3_the_total_follows_the_basket_and_waits_for_every_price(self):
        steps = [{"dish": "Cold brew", "add": 1}, {"dish": "Cold brew", "size": "Large"}, {"dish": "Cold brew", "add": 1},
                 {"dish": "Latte", "add": 1}, {"dish": "Mocha", "add": 1}]
        p = page(answers={"/gor/menu": [MENU]}, steps=steps)
        self.assertEqual([s["total"] for s in p["steps"]],
                         ["Total $4.00", "Total $4.00", "Total $8.50", "Total $11.70", ""])      # Mocha has no price yet
        self.assertEqual(p["steps"][2]["basket"], ["Cold brew · Regular", "Cold brew · Large"])   # the size's own line, named by size

    def test_p4_the_retailers_words_are_in_bdi_and_no_direction_is_guessed(self):
        p = page(answers={"/gor/menu": [MENU]}, steps=[{"dish": "Latte", "add": 1}])
        self.assertEqual(p["whereBdi"], "BDI")
        self.assertTrue(p["bdiWrapped"])
        self.assertEqual((p["dirs"], p["htmlDirs"]), (0, 0))
        with open(os.path.join(os.path.dirname(HERE), "service", "page.js")) as f:
            js = f.read()
        self.assertNotIn('dir="auto"', js)
        self.assertNotIn('.dir = "auto"', js)

    def test_p6_the_total_counts_choices_and_quantity_and_an_answer_is_scrolled_into_view(self):
        spiced = json.loads(json.dumps(MENU))
        spiced["menu"][0]["dishes"][2]["groups"] = [{"group": "Milk", "label": "Milk", "min": 1, "max": 1,
                                                      "choices": [{"code": "OAT", "name": "Oat milk", "price": 0.6}]}]
        steps = [{"dish": "Latte", "menuopen": 1}, {"dish": "Latte", "pick": 1}, {"dish": "Latte", "plus": 0}]
        p = page(answers={"/gor/menu": [spiced]}, steps=steps)
        self.assertEqual(p["steps"][1]["total"], "Total $3.80")                         # 3.20 + oat 0.60
        self.assertEqual(p["steps"][2]["total"], "Total $7.60")                         # two of them
        bad = page(answers={"/gor/menu": [spiced]}, steps=[{"dish": "Latte", "menuopen": 1}, {"dish": "Latte", "pick": 0}])
        self.assertEqual((bad["steps"][1]["note"], bad["steps"][1]["noteBdi"]), ("Milk: choose 1", "BDI"))   # the label in <bdi>
        self.assertEqual(bad["scrolled"], 2)                                            # "Loading", then the answer: both brought into view

    def test_p7_a_picture_that_does_not_load_becomes_the_tile(self):
        p = page(answers={"/gor/menu": [MENU]}, steps=[{"dish": "Latte", "imgerror": 1}])
        self.assertTrue(p["steps"][0]["tile"])

    def test_p5_a_late_price_is_asked_again_and_drawn_while_the_guest_has_taken_nothing(self):
        late = json.loads(json.dumps(MENU))
        late["menu"][0]["dishes"][3]["price"] = 5.0
        p = page(answers={"/gor/menu": [MENU, late]}, steps=[{"dish": "Latte", "again": 1}, {"dish": "Mocha", "add": 1}],
                 )
        self.assertEqual(p["calls"], ["/gor/menu", "/gor/menu"])
        self.assertEqual(p["steps"][1]["total"], "Total $5.00")


if __name__ == "__main__":
    unittest.main()
