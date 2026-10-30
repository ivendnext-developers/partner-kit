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


def line(name, under=None):
    return {"item_code": name.upper(), "item_name": name, "qty": 1, "note": "", "under": under, "guest": "", "course": "",
            "allergens": ""}


def ticket(order, n, dishes, kind="send", choices=0, station="Grill"):
    ls = [line(f"dish {order} {i}") for i in range(dishes)]
    ls[1:1] = [line(f"choice {i}", under=0) for i in range(choices)]
    return {"kitchen_order": order, "ticket": n, "station": station, "kind": kind, "call_number": order, "till": "Till 2",
            "state": "new", "sent_at": "2026-10-30 19:01:00", "lines": ls}


def station(*tickets, lang="en"):
    b = board()
    b["view"] = {"tickets": list(tickets), "recall": []}
    b["look"]["lang"] = lang
    return b


def expo(orders, waiting=0):
    b = station()
    b.update(kind="Expo", stations=[])
    b["view"] = {"orders": orders, "waiting": [{"qty": 1, "item_name": f"w{i}"} for i in range(waiting)]}
    return b


def order(key, tickets, bump=False):
    return {"kitchen_order": key, "call_number": key, "sent_at": "2026-10-30 19:01:00", "bump": bump, "tickets": tickets}


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


@unittest.skipUnless(NODE, "node is not installed")
class PageFit(unittest.TestCase):
    """page.js's own fitting, on the harness's layout (lines and headings 20 high, buttons 30, one column: a
    one-dish station ticket is 110 high)."""

    def fit(self, answer, board_h, inner=1000, steps=()):
        return page("fit", answers={"/ksc/board": [answer]}, layout={"board": board_h, "inner": inner}, steps=list(steps))

    def test_f1_a_dish_with_too_many_choices_folds_its_choices_and_keeps_bump(self):
        got = self.fit(station(ticket("k1", 1, 1, choices=8)), 200)["first"]["slips"][0]
        self.assertEqual((got["more"], got["act"], got["tall"]), ("+5 more choices", True, False))
        self.assertLessEqual(got["height"], 200)

    def test_f2_a_single_dish_taller_than_the_board_scrolls_its_ticket(self):
        got = self.fit(station(ticket("k1", 1, 1, choices=8)), 100)["first"]["slips"][0]
        self.assertEqual((got["tall"], got["more"], got["hiddenLines"]), (True, "", 0))   # whole, and it scrolls
        self.assertLessEqual(got["height"], 100)

    def test_f2c_a_scrolling_ticket_keeps_its_parts_height_so_every_line_shows(self):
        # the browser shrinks a flex child that hides its overflow: the scroll must not squeeze a part away
        css = open(os.path.join(os.path.dirname(HERE), "service", "page.css")).read()
        self.assertIn(".ksc-slip.is-tall > * { flex-shrink: 0; }", css)

    def test_f3_the_expo_never_folds_a_void_and_shows_again_what_fits(self):
        got = self.fit(expo([order("k1", [ticket("k1", 1, 3), ticket("k1", 2, 2, kind="void", station="Bar")])]), 150)
        slip = got["first"]["slips"][0]
        self.assertEqual(slip["voidPart"], [{"shown": True, "lines": 2}])
        self.assertEqual(slip["more"], "+2 more dishes")
        self.assertLessEqual(slip["height"], 150)

    def test_f3b_a_folded_station_heading_frees_room_that_is_used_again(self):
        parts = [ticket("k1", n, 1, station=st) for n, st in ((1, "Grill"), (2, "Fryer"), (3, "Bar"))]
        self.assertEqual(self.fit(expo([order("k1", parts)]), 130)["first"]["slips"][0]["more"], "+1 more dish")

    def test_f4_whole_tickets_paged_in_order_and_none_left_out(self):
        got = self.fit(station(*[ticket(f"k{i}", 1, 1) for i in range(6)]), 340, steps=["next"])
        self.assertEqual(got["first"]["shown"], ["k0.1", "k1.1", "k2.1"])
        self.assertEqual(got["first"]["pager"], {"more": "+3 more tickets", "prev": False, "next": True})
        self.assertEqual(got["next"]["shown"], ["k3.1", "k4.1", "k5.1"])
        self.assertEqual(got["next"]["pager"], {"more": "", "prev": True, "next": False})

    def test_f5_still_to_make_shows_whole_dishes_and_counts_the_rest(self):
        got = self.fit(expo([order("k1", [ticket("k1", 1, 1)])], waiting=20), 500, inner=400)["first"]["strip"]
        self.assertEqual((got["dishes"], got["rest"]), (8, "+12 more dishes"))
        self.assertLessEqual(got["height"], 100)

    def test_f6_a_void_reads_as_one_in_the_whole_ticket_dialog(self):
        got = self.fit(station(ticket("k1", 1, 10, kind="void")), 150, steps=["more:k1.1"])
        self.assertEqual(got["dialog"], {"open": True, "voidBanner": 1, "voidBox": True, "lines": 10})

    def test_f2b_an_expo_void_too_tall_to_fold_scrolls_so_bump_order_stays_in_reach(self):
        o = order("k1", [ticket("k1", 1, 1), ticket("k1", 2, 14, kind="void", station="Bar")], bump=True)
        got = self.fit(expo([o]), 200)["first"]["slips"][0]
        self.assertEqual((got["tall"], got["more"], got["voidPart"], got["hiddenLines"]),
                         (True, "", [{"shown": True, "lines": 14}], 0))
        self.assertLessEqual(got["height"], 200)

    def test_f2d_a_ticket_that_scrolls_anyway_unfolds_what_was_folded(self):
        o = order("k1", [ticket("k1", 1, 3), ticket("k1", 2, 14, kind="void", station="Bar")], bump=True)
        got = self.fit(expo([o]), 200)["first"]["slips"][0]
        self.assertEqual((got["tall"], got["more"], got["hiddenLines"]), (True, "", 0))

    def test_f7_the_board_counts_the_numbers_that_still_do_not_fit(self):
        b = station()
        b.update(kind="Board", stations=[])
        b["view"] = {"preparing": [str(100 + i) for i in range(10)], "ready": []}
        got = self.fit(b, 200)["first"]["numbers"]
        self.assertEqual(got, {"shown": 8, "more": ["+2"]})

    def test_f8_a_ticket_moved_under_the_finger_holds_taps_a_moment(self):
        six = [ticket(f"k{i}", 1, 1) for i in range(6)]
        a, b = station(*six), station(*six[1:])        # another screen bumped k0: every ticket slides up a slot
        got = page("fit", answers={"/ksc/board": [a, b], "/ksc/move": [{"state": "moved", "moved": 1}]},
                   layout={"board": 340, "inner": 1000}, steps=["read", "tap", "wait:1100", "tap"])
        self.assertEqual(got["taps"], [0, 1])

    def test_f8b_the_cooks_own_bump_leaving_holds_nothing(self):
        six = [dict(ticket(f"k{i}", 1, 1), state="ready") for i in range(6)]   # the cook's tap is Bump
        got = page("fit", answers={"/ksc/board": [station(*six), station(*six[1:])],
                                   "/ksc/move": [{"state": "moved", "moved": 1}]},
                   layout={"board": 340, "inner": 1000}, steps=["tap", "tap"])
        self.assertEqual(got["taps"], [1, 2])

    def test_f8e_a_refused_bump_is_not_the_cooks_and_its_later_removal_holds(self):
        six = [dict(ticket(f"k{i}", 1, 1), state="ready") for i in range(6)]
        got = page("fit", answers={"/ksc/board": [station(*six), station(*six), station(*six[1:])],
                                   "/ksc/move": [{"state": "refused", "why": "step"}, {"state": "moved", "moved": 1}]},
                   layout={"board": 340, "inner": 1000}, steps=["tap", "wait:7000", "read", "tap"])
        self.assertEqual(got["taps"], [1, 1])               # the expo bumped k0 after the cook's Bump was refused

    def test_f8c_the_cooks_own_paging_holds_nothing(self):
        six = [ticket(f"k{i}", 1, 1) for i in range(6)]
        got = page("fit", answers={"/ksc/board": [station(*six)], "/ksc/move": [{"state": "moved", "moved": 1}]},
                   layout={"board": 340, "inner": 1000}, steps=["next", "tap"])
        self.assertEqual(got["taps"], [1])

    def test_f8d_a_ticket_the_cook_only_started_leaving_by_another_screen_holds(self):
        six = [ticket(f"k{i}", 1, 1) for i in range(6)]
        started = [dict(six[0], state="started")] + six[1:]
        got = page("fit", answers={"/ksc/board": [station(*six), station(*started), station(*six[1:])],
                                   "/ksc/move": [{"state": "moved", "moved": 1}]},
                   layout={"board": 340, "inner": 1000}, steps=["tap", "read", "tap"])
        self.assertEqual(got["taps"], [1, 1])               # the expo bumped k0: the cook's next tap is held

    def test_f10_a_screen_back_on_the_network_catches_up_on_its_next_read(self):
        six = [ticket(f"k{i}", 1, 1) for i in range(2)]
        got = page("fit", answers={"/ksc/board": [{"state": "unavailable"}, station(*six)]},
                   layout={"board": 340, "inner": 1000}, steps=["read"])
        self.assertEqual((got["first"]["shown"], got["first"]["note"]), ([], "The kitchen's tickets cannot be read right now. "
                                                                          "This screen tries again by itself."))
        self.assertEqual((got["read"]["shown"], got["read"]["note"]), (["k0.1", "k1.1"], ""))

    def test_f11_a_late_ticket_on_another_page_turns_the_page_button_red(self):
        six = [ticket(f"k{i}", 1, 1) for i in range(6)]
        six[5]["sent_at"] = "2026-10-30 18:00:00"           # 65 minutes: late
        self.assertTrue(self.fit(station(*six), 340)["first"]["late"])
        self.assertFalse(self.fit(station(*six[:5]), 340)["first"]["late"])

    def test_f12_a_minute_after_the_last_touch_the_screen_goes_back_to_the_first_page(self):
        six = [ticket(f"k{i}", 1, 1) for i in range(6)]
        got = page("fit", answers={"/ksc/board": [station(*six)]}, layout={"board": 340, "inner": 1000},
                   steps=["next", "wait:61000", "read"])
        self.assertEqual((got["next"]["shown"], got["read"]["shown"]), (["k3.1", "k4.1", "k5.1"], ["k0.1", "k1.1", "k2.1"]))

    def test_f13_a_tap_that_was_not_applied_says_so(self):
        six = [dict(ticket(f"k{i}", 1, 1), state="ready") for i in range(2)]
        got = page("fit", answers={"/ksc/board": [station(*six)], "/ksc/move": [{"state": "unavailable"}]},
                   layout={"board": 340, "inner": 1000}, steps=["tap", "read"])
        self.assertEqual(got["read"]["note"], "The kitchen's tickets cannot be read right now. This screen tries again by itself.")

    def test_f9_arabic_counts_take_their_dual_and_eleven_and_over_forms(self):
        def more(n):
            return self.fit(station(*[ticket(f"k{i}", 1, 1) for i in range(n + 1)], lang="ar"), 120)["first"]["pager"]["more"]
        self.assertEqual([more(1), more(2), more(4), more(12), more(100), more(102), more(103), more(111)],
                         ["+تذكرة واحدة أخرى", "+تذكرتان أخريان", "+4 تذاكر أخرى", "+12 تذكرةً أخرى", "+100 تذكرة أخرى",
                          "+102 تذكرة أخرى", "+103 تذاكر أخرى", "+111 تذكرةً أخرى"])


if __name__ == "__main__":
    unittest.main()
