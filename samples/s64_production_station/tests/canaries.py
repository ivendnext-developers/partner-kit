#!/usr/bin/env python3
"""S64's canaries: each test that guards the press's signature, the station's link, the worker, the price point, the
engine's read-back, today's colour, a cart posted once (the receipt and the transfer found before they are made, the
minute a cart is held, one open cart a station), a taken-back tag kept out, the receipt at no value, the stores of
sell-through and its window, the grouped read's fallback, the page's print and the barcode must go RED when that check
is removed. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one
test named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once,
and a Python mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test).
The runner is S54's (S49's before it): a defect here is a defect there.

    python3 samples/s64_production_station/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S, R, M, J, B = "service/app.py", "pst.py", "manifest.json", "service/page.js", "service/code128.js"
T = "test_service."
RU = "test_rules."
P = "test_page."
MF = "test_manifest.ManifestTest."

CANARIES = [
    # the presses and the link
    ("the press's signature is checked", S,
     "        if not secrets or all(pst.verify(ts, sig, raw, s.decode(), self.now()) for s in secrets):", "        if not secrets:",
     T + "MakeLink.test_a_press_signed_with_another_secret_or_too_old_is_refused"),
    ("a test call never reaches the handler", S, "        if testcall.is_test(headers):", "        if False:",
     T + "MakeLink.test_a_signed_test_call_is_answered_without_the_handler"),
    ("a link made again stops the old one", S, '            if s is not None and (pst.num(s.get("number")) != found[1] or',
     "            if s is not None and (False or", T + "MakeLink.test_a_link_made_again_stops_the_old_one"),
    ("a link's signature is the retailer's", R,
     "        return (record, number) if any(hmac.compare_digest(sign(s, site, record, number), sig) for s in secrets) else None",
     "        return (record, number)", RU + "Links.test_a_link_reads_back_only_with_the_retailers_secret"),
    # a tag
    ("only the settings' active workers tag", S, "        if worker not in pst.workers(settings):", "        if False:",
     T + "Tagging.test_each_refusal_writes_nothing_and_says_what_to_do"),
    ("an inactive worker is not offered", R, ' for r in _rows(settings, "workers") if num(r.get("active")))',
     ' for r in _rows(settings, "workers"))', RU + "Settings.test_only_active_workers_each_once"),
    ("the price is the settings' own", S, '        price = pst.price_of(pst.price_points(settings), category, body.get("price"))',
     '        price = pst.money(body.get("price"))', T + "Tagging.test_each_refusal_writes_nothing_and_says_what_to_do"),
    ("a price point to the cent", R, "    return next((q for q in points[category] if abs(q - p) < 0.005), None)",
     "    return p", RU + "Settings.test_the_price_a_tap_names_must_be_the_categorys_own"),
    ("the engine must read the price back", S, "        if not pst.read_back(resolved, item, price):", "        if False:",
     T + "Tagging.test_a_site_whose_labels_carry_a_price_their_scan_does_not_read_back_prints_nothing"),
    ("the read-back compares the price", R, "    return bool(same) and abs(got - price) < 0.005", "    return bool(same)",
     RU + "Tags.test_the_old_engines_price_and_any_other_item_is_refused"),
    ("the read-back compares the item", R, '    same = (code and code == item["name"]) or (bar and bar in item["barcodes"])',
     "    same = True", RU + "Tags.test_the_old_engines_price_and_any_other_item_is_refused"),
    ("a passed price asks the engine once", S, '        if kept:\n            return kept, ""', '        if False:\n            return kept, ""',
     T + "Tagging.test_a_second_tag_at_a_price_already_read_back_asks_the_engine_nothing"),
    ("an item with no mask is refused", S, '        if not item["mask"]:', "        if False:",
     T + "Tagging.test_an_item_with_no_barcode_mask"),
    ("today is the site's own date", S, '            name = (door.doc("System Settings", "System Settings") or {}).get("time_zone") or SITE_DEFAULT_ZONE',
     '            name = "UTC"', T + "Tagging.test_the_day_and_hour_are_the_sites_own"),
    ("a blank time zone is the site's own default", S, 'SITE_DEFAULT_ZONE = "Asia/Kolkata"', 'SITE_DEFAULT_ZONE = "UTC"',
     T + "Tagging.test_a_site_with_no_time_zone_set_keeps_its_own_default_zones_day"),
    ("the colours turn each week", R, "    return cs[weeks % len(cs)], first + datetime.timedelta(days=7 * weeks)",
     "    return cs[0], first + datetime.timedelta(days=7 * weeks)",
     RU + "Colours.test_the_colours_turn_each_week_in_the_leads_order_and_start_again"),
    ("the lead's colour for one day", R, "    if one and on == day:", "    if False:",
     RU + "Colours.test_the_leads_colour_for_one_day_wins_on_that_day_only"),
    ("undo takes back an unsent, live tag only", S,
     '        return [["station", "=", station], ["cart", "is", "not set"], ["void", "=", 0]]',
     '        return [["station", "=", station], ["cart", "is", "not set"]]',
     T + "Tagging.test_undo_takes_back_the_last_tag_of_this_cart_only"),
    # Cart full: the stock
    ("a receipt already naming the cart is taken", S, '        se = self._posted(door, name, "Material Receipt")', "        se = None",
     T + "Carts.test_a_retry_after_a_lost_answer_takes_the_receipt_made_and_posts_it_once"),
    ("a transfer already naming the cart is taken", S, '        se = self._posted(door, name, "Material Transfer")', "        se = None",
     T + "Carts.test_a_lost_answer_after_the_transfer_posts_nothing_twice"),
    ("only a submitted entry is taken", S, '["purpose", "=", purpose],\n                                                  ["docstatus", "=", 1]]',
     '["purpose", "=", "Material Receipt"]]', T + "Carts.test_cart_full_receives_at_no_value_into_the_room_then_moves_the_same_lines_to_the_store"),
    ("a cart written this minute is held", S, "            if self._fresh(door, site, mine[-1]):", "            if False:",
     T + "Carts.test_a_tap_while_another_posts_this_stations_cart_is_told_busy"),
    ("one open cart a station", S, "                if e.kind == TWICE:", "                if False:",
     T + "Carts.test_two_calls_at_once_make_one_cart"),
    ("an unfinished cart is continued", S, "        mine = [c for c in carts if not pst.finished(c, room)]", "        mine = []",
     T + "Carts.test_a_failure_between_the_two_entries_leaves_the_cart_received_and_a_repeat_finishes_it"),
    ("a cart kept in the room is received only", S, '        if cart.get("state") == "Received" and cart.get("destination") != room:',
     '        if cart.get("state") == "Received":', T + "Carts.test_a_cart_kept_in_the_room_is_received_only_and_the_next_cart_starts"),
    ("a kept cart lets the next one start", S, '            done["open_for"] = None', "            pass",
     T + "Carts.test_a_cart_kept_in_the_room_is_received_only_and_the_next_cart_starts"),
    ("a cart just sent is told again, not posted", S,
     "                if carts and self._fresh(door, site, carts[0]) and pst.finished(carts[0], room):", "                if False:",
     T + "Carts.test_a_double_tap_posts_nothing_twice"),
    ("an empty cart is refused", S, '                return _refused("empty")\n            try:', "                pass\n            try:",
     T + "Carts.test_an_empty_cart_and_a_place_not_listed_are_refused"),
    ("only a listed place", S, "            if to not in named:", "            if False:",
     T + "Carts.test_an_empty_cart_and_a_place_not_listed_are_refused"),
    ("a taken-back tag is never received", R, '        if not isinstance(t, dict) or num(t.get("void")) or not isinstance(t.get("item"), str)',
     '        if not isinstance(t, dict) or not isinstance(t.get("item"), str)',
     RU + "Carts.test_lines_by_item_and_a_taken_back_tag_is_never_received"),
    ("the receipt is at no value", R, '"t_warehouse": room, "basic_rate": 0, "allow_zero_valuation_rate": 1}',
     '"t_warehouse": room, "basic_rate": 1, "allow_zero_valuation_rate": 1}',
     T + "Carts.test_cart_full_receives_at_no_value_into_the_room_then_moves_the_same_lines_to_the_store"),
    ("the move takes the receipt's own lines", S, '            lines = [(r["item_code"], r["qty"]) for r in items]',
     '            lines = [(r["item_code"], 1) for r in items]',
     T + "Carts.test_cart_full_receives_at_no_value_into_the_room_then_moves_the_same_lines_to_the_store"),
    # Work out
    ("a taken-back tag is not counted", S, '[["station", "in", stations], ["void", "=", 0], ["tagged_on", ">=", frm.isoformat()],',
     '[["station", "in", stations], ["tagged_on", ">=", frm.isoformat()],',
     T + "WorkOut.test_the_rows_by_worker_add_up_to_the_tags_and_the_cart"),
    ("hours are the distinct clock hours", R, '        hours = len(a["hours"])', "        hours = 1",
     RU + "Report.test_worker_rows_pieces_hours_and_per_hour"),
    ("sold counts the stores only", S, '["custom_is_retail_store", "=", 1]], limit=500)]', "], limit=500)]",
     T + "WorkOut.test_sell_through_reads_the_colours_items_in_the_stores_in_the_weeks_window"),
    ("sold ends today when the turn is later", R, "    return week_start, min(end, today)", "    return week_start, end",
     T + "WorkOut.test_sell_through_reads_the_colours_items_in_the_stores_in_the_weeks_window"),
    ("a refused grouped read pages through", S, "            if not e.refused or e.code in (401, 403):\n                raise",
     "            raise", T + "WorkOut.test_a_shop_that_refuses_a_grouped_read_is_read_a_page_at_a_time_with_the_same_rows"),
    ("a refused report is said in words", S, '        except ReportRefused:\n            return 200, pst.message(REPORT_REFUSED, "warning")',
     "        except ReportRefused:\n            raise", T + "WorkOut.test_a_refused_report_is_said_in_words"),
    ("a report's dates are checked first", S, "        if frm is None or to is None or frm > to:", "        if frm is None or to is None:",
     T + "WorkOut.test_a_misfilled_report_says_what_to_fix_and_reads_no_tag"),
    # the manifest
    ("the app's role may submit its stock entries", M, '    "create",\n    "submit"\n   ]', '    "create"\n   ]',
     MF + "test_the_rights_the_service_needs_and_no_more"),
    ("one open cart a station, in the record", M, '     "unique": 1,\n     "length": 140,', '     "length": 140,',
     MF + "test_a_cart_has_one_open_cart_a_station_and_pounds_a_lead_types"),
    ("the feed registration is frozen", M, '"description": "the production station service reads the settings and items',
     '"description": "the service reads the settings and items', MF + "test_the_feed_registration_is_frozen"),
    # the page and its barcode
    ("the lead's one-day colour reads as today's", J, 'w(a.one_day ? "today" : "thisWeek", { colour: a.colour })',
     'w("thisWeek", { colour: a.colour })', P + "Station.test_the_leads_colour_for_one_day_reads_as_todays"),
    ("the tag prints the service's price", J, '    $("tag-price").textContent = money(t.price);', '    $("tag-price").textContent = money(0);',
     P + "Station.test_one_tap_on_a_price_prints_one_tag_as_the_service_answered_it"),
    ("the tag's page size from the settings", J, 'sh.insertRule("@page { size: " + want + "; margin: 0; }", sh.cssRules.length); sized = want;',
     "sized = want;", P + "Station.test_one_tap_on_a_price_prints_one_tag_as_the_service_answered_it"),
    ("the page's title comes back after a print", J, "    try { window.print(); } finally { document.title = title; }",
     "    window.print();", P + "Station.test_one_tap_on_a_price_prints_one_tag_as_the_service_answered_it"),
    ("the category stays chosen", J, "        printTag(a.tag); count += 1;", '        printTag(a.tag); count += 1; category = "";',
     P + "Station.test_the_category_stays_chosen_so_the_next_piece_is_one_tap"),
    ("a refused tag prints nothing", J, '      if (a.state === "tagged") {\n        printTag(a.tag);', '      if (true) {\n        printTag(a.tag);',
     P + "Station.test_a_refused_tag_prints_nothing_and_says_what_to_do"),
    ("the retailer's words keep their direction", J, '    b.setAttribute("dir", "auto");', "",
     P + "Station.test_the_retailers_words_keep_their_own_direction"),
    ("a replaced link does not retry", J, '        if (a.state !== "unknown") timer = setTimeout(read, RETRY_MS);',
     "        timer = setTimeout(read, RETRY_MS);", P + "Station.test_a_replaced_link_says_so_and_does_not_retry"),
    ("the barcode's checksum", B, "    out.push(sum % 103);", "    out.push(sum % 101);",
     P + "Barcode.test_code_set_b_and_its_checksum"),
    ("a tag's digits in code set C", B, "    if (/^[0-9]+$/.test(s) && s.length >= 4) {", "    if (false) {",
     P + "Barcode.test_a_tags_digits_in_code_set_c_with_a_last_odd_digit_in_b"),
    ("only printable ASCII", B, '      if (c < 32 || c > 126) throw new Error("Code 128 B carries printable ASCII only");', "",
     P + "Barcode.test_a_character_code_128_b_does_not_carry_is_refused"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s64-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local", "screenshots"))
        for sub in ("tools/manifest", "tools/app_template", "tools/contracts", "contracts"):
            shutil.copytree(os.path.join(kit, sub), os.path.join(tmp, "r", sub), ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f, encoding="utf-8").read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        open(f, "w", encoding="utf-8").write(src.replace(anchor, mutant))
        if f.endswith(".py"):
            py_compile.compile(f, doraise=True)
        p = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                           capture_output=True, text=True, timeout=120)
        last = (p.stderr.strip().splitlines() or [""])[-1]
        return ("RED" if p.returncode else "GREEN"), last
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    bad = 0
    for c in CANARIES:
        verdict, last = run(*c)
        bad += verdict != "RED"
        print(f"{verdict:6} {c[0]} — {c[4]} — {last}")
    print(f"{len(CANARIES) - bad} of {len(CANARIES)} canaries RED")
    sys.exit(1 if bad else 0)
