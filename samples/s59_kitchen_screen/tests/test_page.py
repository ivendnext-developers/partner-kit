#!/usr/bin/env python3
"""S59's page rules, run under node: the fitting rules in ``service/fit.js`` (the four size steps, a page of whole
tickets, a ticket folded behind "+N more dishes") and, through ``tests/page_harness.js`` (a small stand-in for the
browser that lays nothing out), the page's own: the size it opens at and what A- / A+ keep on the device, a blocked
device store, a held refusal, and the retailer's words in ``<bdi>`` with no ``dir="auto"``. Skipped where node is
missing; CI's runners have it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
FIT = os.path.join(os.path.dirname(HERE), "service", "fit.js")
NODE = shutil.which("node")
KEY = "ksc.size.bistro.example.com.KSC-SCREEN-00001"


def fit(expr: str):
    """Evaluate one expression over fit.js's rules (``f``) and return its JSON value."""
    code = f"const f = require({json.dumps(FIT)}); process.stdout.write(JSON.stringify({expr}));"
    return json.loads(subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True, timeout=30).stdout)


def page(scenario: str, **opts):
    out = subprocess.run([NODE, os.path.join(HERE, "page_harness.js"), scenario, json.dumps(opts)],
                         capture_output=True, text=True, timeout=30)
    value = json.loads(out.stdout or "{}")
    assert "error" not in value, value.get("error")
    return value


def board(size="standard", note="", name="Steak"):
    line = {"item_code": "STEAK", "item_name": name, "qty": 1, "note": note, "under": None, "guest": "2",
            "course": "Mains", "allergens": "Allergens: sesame"}
    ticket = {"kitchen_order": "ko2", "ticket": 1, "station": "Grill", "kind": "send", "call_number": "Table 12",
              "till": "Till 2", "state": "new", "sent_at": "2026-10-30 19:01:00", "lines": [line]}
    return {"state": "open", "kind": "Station", "title": "Grill", "stations": ["Grill"], "as_of": "2026-10-30 19:05:00",
            "look": {"mode": "dark", "accent": "", "lang": "ar", "warn": 8, "late": 15, "size": size},
            "view": {"tickets": [ticket], "recall": []}}


@unittest.skipUnless(NODE, "node is not installed")
class FitRules(unittest.TestCase):
    def test_p1_a_screen_takes_the_cooks_size_then_the_stores_then_standard(self):
        self.assertEqual(fit('[f.size("large", "compact"), f.size("huge", "compact"), f.size("", "x"), f.size(null)]'),
                         ["large", "compact", "standard", "standard"])

    def test_p2_a_minus_and_a_plus_stop_at_the_ends(self):
        self.assertEqual(fit('[f.step("compact", -1), f.step("compact", 1), f.step("xlarge", 1), f.step("junk", 1)]'),
                         ["compact", "standard", "xlarge", "large"])

    def test_p3_a_page_ends_before_the_first_ticket_that_passes_the_bottom_and_holds_at_least_one(self):
        self.assertEqual(fit("[f.fits([100, 200, 300], 250), f.fits([900, 950], 500), f.fits([], 500), f.fits([10, 20], 500)]"),
                         [2, 1, 0, 2])

    def test_p4_pages_cover_every_ticket_in_order_and_stop_at_the_last(self):
        # five tickets 100 high, two to a page: pages [0,2), [2,4), [4,5); asking for page 9 shows the last
        layout = "(from) => [100, 200, 300, 400, 500].slice(from).map((b) => b - from * 100)"
        got = fit(f"[0, 1, 2, 9].map((p) => f.pages(5, p, {layout}, 250))")
        self.assertEqual(got, [{"page": 0, "from": 0, "end": 2}, {"page": 1, "from": 2, "end": 4},
                               {"page": 2, "from": 4, "end": 5}, {"page": 2, "from": 4, "end": 5}])
        self.assertEqual(fit("f.pages(0, 3, () => [], 250)"), {"page": 0, "from": 0, "end": 0})

    def test_p5_a_tall_ticket_folds_its_last_dishes_and_keeps_the_first(self):
        self.assertEqual(fit("[f.trim([40, 40, 40], 200, 130), f.trim([40, 40, 40], 200, 10), f.trim([40], 300, 10), "
                             "f.trim([40, 40], 100, 100)]"), [2, 2, 0, 0])


@unittest.skipUnless(NODE, "node is not installed")
class PageRules(unittest.TestCase):
    def test_q1_the_store_default_then_the_cooks_choice_kept_on_this_device(self):
        got = page("size", answers={"/ksc/board": [board("large")]}, taps=["bigger"])
        self.assertEqual((got["first"], got["after"], got["biggerDisabled"]), ("large", "xlarge", True))
        self.assertEqual(got["stored"], {KEY: "xlarge"})
        got = page("size", storage={KEY: "compact"}, answers={"/ksc/board": [board("large")]}, taps=["smaller"])
        self.assertEqual((got["first"], got["after"], got["smallerDisabled"]), ("compact", "compact", True))
        got = page("size", storage={KEY: "enormous"}, answers={"/ksc/board": [board("large")]})
        self.assertEqual(got["first"], "large")                               # a value it does not know is ignored

    def test_q2_a_blocked_device_store_still_opens_and_sizes_the_screen(self):
        got = page("size", storage="throws", answers={"/ksc/board": [board("compact")]}, taps=["bigger"])
        self.assertEqual((got["first"], got["after"]), ("compact", "standard"))

    def test_q3_a_tap_with_no_answer_does_not_take_down_a_held_refusal(self):
        got = page("held", answers={"/ksc/board": [board()],
                                    "/ksc/move": [{"state": "refused", "why": "step"}, {"state": "unavailable"}]})
        self.assertTrue(got["drawn"])
        self.assertEqual(got["moves"], 2)
        self.assertFalse(got["afterRefusal"]["hidden"])
        self.assertEqual(got["afterSecond"], got["afterRefusal"])

    def test_q4_the_retailers_words_are_isolated_and_nothing_is_dir_auto(self):
        got = page("words", answers={"/ksc/board": [board(note="well done", name="ستيك")]})
        self.assertEqual(got["dirAuto"], 0)
        for words in ("Grill", "Table 12", "ستيك", "well done", "Allergens: sesame", "Till 2"):
            self.assertIn(words, got["bdi"])


if __name__ == "__main__":
    unittest.main()
