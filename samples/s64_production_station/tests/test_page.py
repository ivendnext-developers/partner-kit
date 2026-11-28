#!/usr/bin/env python3
"""S64's page and its barcode, run under node: the Code 128 encoder (``service/code128.js``) on known values, and the
station's page (``service/page.js``) through ``tests/page_harness.js``, a small stand-in for the browser: the worker's
name first and kept on the device, a category that stays chosen, one tap one tag printed with the service's price and
barcode, undo, Cart full and its places, the refusals in the worker's words, the tag's size from the settings, and the
retailer's words with dir="auto". Skipped where node is missing; CI's runners have it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
CODE = os.path.join(os.path.dirname(HERE), "service", "code128.js")
NODE = shutil.which("node")
TOO_OLD = "This price cannot be printed on a tag yet. Tell your lead: iVendNext needs an update."


def js(expr: str):
    code = f"const c = require({json.dumps(CODE)}); process.stdout.write(JSON.stringify({expr}));"
    return json.loads(subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True, timeout=30).stdout)


def page(**opts):
    out = subprocess.run([NODE, os.path.join(HERE, "page_harness.js"), json.dumps(opts)], capture_output=True, text=True,
                         timeout=30)
    value = json.loads(out.stdout or "{}")
    assert "error" not in value, value.get("error")
    return value


BOARD = {"state": "open", "title": "Station 3", "colour": "Blue", "workers": ["Ana", "Ben"], "cart": 4,
         "categories": [{"name": "Women's tops", "prices": [4.99, 6.99, 19.99]}, {"name": "Men's shirts", "prices": [6.99]}],
         "places": [{"warehouse": "Store 12 - GW", "label": "Store 12"}, {"warehouse": "Processing room - GW", "label": "Keep here"}],
         "tag": {"width_mm": 58, "height_mm": 32}, "currency": "USD"}
TAG = {"state": "tagged", "tag": {"name": "PST-T-00000042", "price": 19.99, "category": "Women's tops", "colour": "Blue",
                                  "barcode": "2970102019990"}}
KEY = "pst.worker.thrift.example.com.PST-S-00001"


@unittest.skipIf(NODE is None, "node is not installed")
class Barcode(unittest.TestCase):
    def test_every_pattern_is_six_widths_of_eleven_modules_and_the_stop_thirteen(self):
        self.assertEqual(js("[c.PATTERNS.length, new Set(c.PATTERNS).size]"), [107, 107])
        self.assertTrue(js("c.PATTERNS.slice(0, 106).every(p => p.length === 6 && [...p].reduce((a, b) => a + +b, 0) === 11)"))
        self.assertEqual(js("[c.PATTERNS[106], [...c.PATTERNS[106]].reduce((a, b) => a + +b, 0)]"), ["2331112", 13])
        self.assertEqual(js("[c.PATTERNS[0], c.PATTERNS[103], c.PATTERNS[104], c.PATTERNS[105]]"),
                         ["212222", "211412", "211214", "211232"])

    def test_code_set_b_and_its_checksum(self):
        # start B 104; P=48 J=42 J=42 1=17 2=18 3=19 C=35: 104 + 48 + 84 + 126 + 68 + 90 + 114 + 245 = 879, 879 mod 103 = 55
        self.assertEqual(js('c.values("PJJ123C")'), [104, 48, 42, 42, 17, 18, 19, 35, 55, 106])

    def test_a_tags_digits_in_code_set_c_with_a_last_odd_digit_in_b(self):
        # start C 105; 29 70 10 10 05 99, CODE B 100, "1" = 17: 105 + 29 + 140 + 30 + 40 + 25 + 594 + 700 + 136 = 1799, mod 103 = 48
        self.assertEqual(js('c.values("2970101005991")'), [105, 29, 70, 10, 10, 5, 99, 100, 17, 48, 106])
        self.assertEqual(js('c.values("123456")'), [105, 12, 34, 56, (105 + 12 + 68 + 168) % 103, 106])
        self.assertEqual(js('c.values("123")')[0], 104)          # three digits: B is shorter

    def test_the_widths_and_the_svgs_bars(self):
        self.assertEqual(js('c.widths("2970101005991").reduce((a, b) => a + b, 0)'), 11 * 10 + 13)
        svg = js('(function(){ const el = t => ({t, a: {}, k: [], setAttribute(k, v) { this.a[k] = v }, appendChild(x) { this.k.push(x) }});'
                 ' const s = c.svg({createElementNS: (n, t) => el(t)}, "PJJ123C", 11); return [s.a.viewBox, s.a.height, s.k.length,'
                 ' s.k[0].a.x, s.k.every(r => r.a.fill === "currentColor")]; })()')
        self.assertEqual(svg, ["0 0 " + str(11 * 9 + 13 + 20) + " 10", "11mm", 3 * 9 + 4, "10", True])   # 9 symbols and the stop

    def test_the_whole_table_is_the_standards(self):
        # the 107 patterns, joined by commas, hashed: the table a real decoder (zbarimg) read back on the bench and the
        # laptop; a changed width anywhere changes it
        got = subprocess.run([NODE, "-e", f'const c = require({json.dumps(CODE)}); process.stdout.write(require("crypto")'
                              '.createHash("sha256").update(c.PATTERNS.join(",")).digest("hex"))'],
                             capture_output=True, text=True, check=True).stdout
        self.assertEqual(got, "e7c485b7f79b124f215d4e34973742632bd63edace80b79bcae8c605f9f4cdab")

    def test_a_character_code_128_b_does_not_carry_is_refused(self):
        out = subprocess.run([NODE, "-e", f'require({json.dumps(CODE)}).values("caf\\u00e9")'], capture_output=True, text=True)
        self.assertNotEqual(out.returncode, 0)
        self.assertIn("printable ASCII", out.stderr)


@unittest.skipIf(NODE is None, "node is not installed")
class Station(unittest.TestCase):
    def test_the_worker_taps_their_name_first_and_it_is_kept_on_the_device(self):
        a = page(answers={"/pst/board": [BOARD]})
        self.assertEqual((a["title"], a["colour"], a["workersTitle"]), ("Station 3", "This week: Blue", "Tap your name"))
        self.assertEqual([t["text"] for t in a["tiles"]], ["Ana", "Ben"])
        self.assertIsNone(a["count"])
        b = page(answers={"/pst/board": [BOARD]}, steps=["tap:Ben"])
        self.assertEqual((b["who"], b["store"][KEY]), ("Ben", "Ben"))
        self.assertEqual([t["text"] for t in b["tiles"]], ["Women's tops", "Men's shirts"])
        c = page(answers={"/pst/board": [BOARD]}, storage={KEY: "Ana"})
        self.assertEqual(c["who"], "Ana")
        d = page(answers={"/pst/board": [BOARD]}, storage={KEY: "Zed"})       # a name no longer active: asked again
        self.assertEqual(d["workersTitle"], "Tap your name")
        e = page(answers={"/pst/board": [BOARD]}, storage="throws", steps=["tap:Ana"])   # a blocked device store
        self.assertEqual(e["who"], "Ana")

    def test_one_tap_on_a_price_prints_one_tag_as_the_service_answered_it(self):
        a = page(answers={"/pst/board": [BOARD], "/pst/tag": [TAG]}, storage={KEY: "Ana"},
                 steps=["tap:Women's tops", "tap:$19.99"])
        (call,) = [c for c in a["calls"] if c["path"] == "/pst/tag"]
        self.assertEqual({k: call[k] for k in ("worker", "category", "price", "s")},
                         {"worker": "Ana", "category": "Women's tops", "price": 19.99, "s": "thrift.example.com"})
        (p,) = a["prints"]
        self.assertEqual((p["price"], p["what"], p["digits"], p["title"]),
                         ("$19.99", "Women's tops · Blue", "2970102019990", "tag PST-T-00000042"))
        self.assertEqual((p["bars"], p["width"], p["height"]), (3 * 10 + 4, "58mm", "32mm"))
        self.assertEqual(a["docTitle"], "Production station")      # the title is the page's again after the print
        self.assertEqual((a["count"], a["note"], a["noteGood"], a["printed"]),
                         ("In this cart: 5", "Printed: $19.99 Women's tops", True, "1"))
        self.assertEqual(a["rules"], ["@page { size: 58mm 32mm; margin: 0; }"])

    def test_the_category_stays_chosen_so_the_next_piece_is_one_tap(self):
        a = page(answers={"/pst/board": [BOARD], "/pst/tag": [TAG]}, storage={KEY: "Ana"},
                 steps=["tap:Women's tops", "tap:$19.99", "tap:$19.99", "tap:$19.99"])
        self.assertEqual(len(a["prints"]), 3)
        self.assertEqual([t["on"] for t in a["tiles"]][:2], [True, False])
        self.assertEqual(a["count"], "In this cart: 7")

    def test_a_double_tap_before_the_answer_prints_one_tag(self):
        a = page(answers={"/pst/board": [BOARD], "/pst/tag": [TAG]}, storage={KEY: "Ana"},
                 steps=["tap:Women's tops", "double:$19.99"])
        self.assertEqual((len([c for c in a["calls"] if c["path"] == "/pst/tag"]), len(a["prints"])), (1, 1))

    def test_a_refused_tag_prints_nothing_and_says_what_to_do(self):
        cases = [({"state": "refused", "why": "too_old"}, TOO_OLD),
                 ({"state": "refused", "why": "no_item", "colour": "Blue", "category": "Women's tops"},
                  "No Women's tops item has this week's colour (Blue). Tell your lead."),
                 ({"state": "unavailable"}, "That tag did not come back. Tap the same price again: it prints and counts once.")]
        for answer, words in cases:
            a = page(answers={"/pst/board": [BOARD], "/pst/tag": [answer]}, storage={KEY: "Ana"},
                     steps=["tap:Women's tops", "tap:$19.99"])
            self.assertEqual((a["prints"], a["note"], a["count"]), ([], words, "In this cart: 4"), answer)

    def test_undo_takes_one_back(self):
        a = page(answers={"/pst/board": [BOARD], "/pst/undo": [{"state": "undone", "tag": {"price": 6.99, "category": "Men's shirts"}}]},
                 storage={KEY: "Ana"}, steps=["click:undo"])
        self.assertEqual((a["count"], a["note"]), ("In this cart: 3", "Taken back: $6.99 Men's shirts"))
        b = page(answers={"/pst/board": [BOARD], "/pst/undo": [{"state": "refused", "why": "no_undo"}]}, storage={KEY: "Ana"},
                 steps=["click:undo"])
        self.assertEqual((b["count"], b["note"]), ("In this cart: 4", "No tag to take back since the last cart."))

    def test_cart_full_asks_where_and_sends_it(self):
        sent = {"state": "sent", "cart": "PST-C-00007", "pieces": 4, "place": "Store 12", "kept": False}
        a = page(answers={"/pst/board": [BOARD], "/pst/cart": [sent]}, storage={KEY: "Ana"}, steps=["click:full"])
        self.assertTrue(a["dialogOpen"])
        self.assertEqual([t["text"] for t in a["tiles"]][-2:], ["Store 12", "Keep here"])
        b = page(answers={"/pst/board": [BOARD], "/pst/cart": [sent]}, storage={KEY: "Ana"}, steps=["click:full", "tap:Store 12"])
        (call,) = [c for c in b["calls"] if c["path"] == "/pst/cart"]
        self.assertEqual(call["warehouse"], "Store 12 - GW")
        self.assertEqual((b["dialogOpen"], b["count"], b["note"]),
                         (False, "In this cart: 0", "Cart PST-C-00007: 4 pieces sent to Store 12."))
        c = page(answers={"/pst/board": [BOARD], "/pst/cart": [{"state": "busy"}]}, storage={KEY: "Ana"},
                 steps=["click:full", "tap:Store 12"])
        self.assertEqual((c["count"], c["note"]), ("In this cart: 4", "This cart is being sent. Wait a minute, then tap Cart full again."))

    def test_a_tap_whose_answer_was_lost_is_sent_again_as_the_same_tap(self):
        a = page(answers={"/pst/board": [BOARD], "/pst/tag": [{"state": "unavailable"}, TAG]}, storage={KEY: "Ana"},
                 steps=["tap:Women's tops", "tap:$19.99", "tap:$19.99", "tap:$19.99"])
        reqs = [c["req"] for c in a["calls"] if c["path"] == "/pst/tag"]
        self.assertEqual(reqs[0], reqs[1])                       # the lost tap, sent again
        self.assertNotEqual(reqs[1], reqs[2])                    # a new tap after the answer came
        self.assertEqual(len(a["prints"]), 2)
        self.assertEqual(a["steps"][1]["note"], "That tag did not come back. Tap the same price again: it prints and counts once.")

    def test_undo_names_the_last_tag_printed(self):
        undone = {"state": "undone", "tag": {"name": "PST-T-00000042", "price": 19.99, "category": "Women's tops"}}
        a = page(answers={"/pst/board": [BOARD], "/pst/tag": [TAG], "/pst/undo": [{"state": "unavailable"}, undone, {"state": "refused", "why": "no_undo"}]},
                 storage={KEY: "Ana"}, steps=["tap:Women's tops", "tap:$19.99", "click:undo", "click:undo", "click:undo"])
        tags = [c.get("tag") for c in a["calls"] if c["path"] == "/pst/undo"]
        self.assertEqual(tags, ["PST-T-00000042", "PST-T-00000042", None])   # the same tag after a lost answer; then none named
        self.assertEqual(a["count"], "In this cart: 4")                      # 4 + 1 printed - 1 taken back

    def test_prices_read_the_same_on_every_device(self):
        a = page(answers={"/pst/board": [BOARD], "/pst/tag": [TAG]}, languages=["es-MX"], storage={KEY: "Ana"},
                 steps=["tap:Women's tops", "tap:$19.99"])
        self.assertEqual(a["prints"][0]["price"], "$19.99")

    def test_a_half_filled_settings_says_what_is_missing(self):
        a = page(answers={"/pst/board": [dict(BOARD, workers=[])]})
        self.assertEqual(a["workersTitle"], "No workers are set up for this station. Tell your lead.")
        b = page(answers={"/pst/board": [dict(BOARD, categories=[])]}, storage={KEY: "Ana"})
        self.assertEqual(b["note"], "No price points are set up. Tell your lead.")
        c = page(answers={"/pst/board": [dict(BOARD, colour="")]})
        self.assertEqual(c["colour"], "No colour this week. Tell your lead.")

    def test_a_board_read_that_fails_says_so_and_clears_when_one_succeeds(self):
        a = page(answers={"/pst/board": [{"state": "unavailable"}]})
        self.assertEqual(a["note"], "Cannot reach iVendNext. Trying again.")
        b = page(answers={"/pst/board": [{"state": "unavailable"}, BOARD]}, steps=["timer:5000"])
        self.assertEqual(b["note"], "")

    def test_the_retailers_words_keep_their_own_direction(self):
        a = page(answers={"/pst/board": [dict(BOARD, workers=["علي"])]})
        self.assertEqual([(t["text"], t["dir"]) for t in a["tiles"]], [("علي", "auto")])

    def test_the_leads_colour_for_one_day_reads_as_todays(self):
        a = page(answers={"/pst/board": [dict(BOARD, colour="Green", one_day=True)]})
        self.assertEqual(a["colour"], "Today: Green")

    def test_a_spanish_station_reads_its_own_words(self):
        a = page(answers={"/pst/board": [BOARD]}, languages=["es-MX"], storage={KEY: "Ana"})
        self.assertEqual((a["lang"], a["colour"], a["count"], a["words"]),
                         ("es", "Esta semana: Blue", "En este carro: 4",
                          {"undo": "Deshacer la última etiqueta", "full": "Carro lleno", "change": "Cambiar de persona"}))

    def test_a_link_with_nothing_after_the_hash_calls_nothing(self):
        a = page(hash="")
        self.assertEqual((a["calls"], a["note"]), ([], "This station's link does not work, or it was replaced. "
                                                        "Ask your lead for the station's new link."))

    def test_a_replaced_link_says_so_and_does_not_retry(self):
        a = page(answers={"/pst/board": [{"state": "unknown"}]})
        self.assertIn("replaced", a["note"])
        self.assertEqual(a["timers"], [])

    def test_every_word_key_has_a_spanish_word(self):
        src = open(os.path.join(os.path.dirname(HERE), "service", "page.js"), encoding="utf-8").read()
        import re
        en = re.search(r"en: \{(.*?)\},\n    es:", src, re.S).group(1)
        es = re.search(r"es: \{(.*?)\}\n  \};", src, re.S).group(1)
        keys = lambda s: sorted(set(re.findall(r"(\w+): \"", s)))  # noqa: E731
        self.assertEqual(keys(en), keys(es))


if __name__ == "__main__":
    unittest.main()
