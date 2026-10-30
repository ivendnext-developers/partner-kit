#!/usr/bin/env python3
"""S59's canaries: each test that guards a retailer's secret, a link's signature, its number and what it was made for,
the store and station fences on a move, the step rules, the expo's and the board's limits, sold out at the screen's own
store, the shared read, or the page's own rules must go RED when that check is removed. For each mutation this copies
the sample (and the kit folders it uses) to a temporary folder, runs the one test named on the unmutated copy (it must
pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs the test
again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S56's.

    python3 samples/s59_kitchen_screen/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, R, F = "test_service.ServiceTest.", "test_many_shops.", "test_rules.Rules.", "test_manifest.ManifestTest."
FR, PR, PF = "test_page.FitRules.", "test_page.PageRules.", "test_page.PageFit."
S, C, FIT, PAGE = "service/app.py", "ksc.py", "service/fit.js", "service/page.js"
L, LS, SS, PL = "test_live.", "live/live.py", "live/sitesocket.py", "test_page.PageLive."

CANARIES = [
    # the press and the retailer
    ("the press's signature is checked", S, "        if not secrets or all(ksc.verify(ts, sig, raw, s.decode()) for s in secrets):",
     "        if not secrets:", T + "test_l1_an_unsigned_or_wrongly_signed_press_is_refused"),
    ("a press stamped long ago is refused", C, " or abs((now or time.time()) - int(ts)) > SKEW_S:", ":",
     T + "test_l1_an_unsigned_or_wrongly_signed_press_is_refused"),
    ("a press names its own record type", C, ' or rec.get("doctype") != doctype', "",
     T + "test_l6_a_press_on_another_record_type_is_refused_before_anything_is_read"),
    ("the link's secret is the link button's", S, 'secrets = shops.secrets_for(record, f"{self.app}:sub:{SUB}")',
     'secrets = [v.encode() for k, v in (record or {}).get("secrets", {}).items() if not k.startswith("user:")]',
     M + "ManyShops.test_another_retailers_link_is_refused"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a redirect is never followed", S, "host\n        return None\n", "host\n        return super().redirect_request(*a, **k)\n",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a record name is one path segment", S, '"/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))',
     'urllib.parse.quote(path, safe="/")', M + "ShopApi.test_a_record_name_is_one_path_segment"),
    ("the library needs its prefix", S, "        if self.app and not prefix:", "        if False:",
     M + "ManyShops.test_the_library_needs_its_prefix"),
    # Make link
    ("Make link raises the number", S, '            number = ksc.num(s.get("number")) + 1',
     '            number = ksc.num(s.get("number")) or 1', T + "test_l3_make_link_again_stops_the_old_link_within_its_keep"),
    ("a station screen needs a station", S, "            if s[\"kind\"] == ksc.KIND_STATION and not ksc.stations_of(s):",
     "            if False:", T + "test_l4_a_station_screen_with_no_station_gets_no_link"),
    ("Make link keeps the screen's own modified", S, '"made_for": ksc.made_for(s),\n                                                     "modified": s.get("modified")}',
     '"made_for": ksc.made_for(s)}', T + "test_l5_a_screen_changed_a_moment_ago_is_not_overwritten"),
    ("a refused app user is said", S, "            if e.code in (401, 403):    # the retailer refused the app's user: say so",
     "            if False:", T + "test_l7_a_refused_app_user_is_said_plainly"),
    # the link
    ("the link's signature is checked", C, "        return (record, number) if any(hmac.compare_digest(sign(s, site, record, number), sig) for s in secrets) else None",
     "        return (record, number)", T + "test_g1_a_forged_or_edited_link_is_refused_before_the_shop_is_read"),
    ("the signature covers the number", C, 'f"ksc1|{site}|{record}|{number}"', 'f"ksc1|{site}|{record}"',
     R + "test_r1_a_link_is_the_retailers_own_signature_for_that_site_record_and_number"),
    ("the signature covers the site", C, 'f"ksc1|{site}|{record}|{number}"', 'f"ksc1|{record}|{number}"',
     R + "test_r1_a_link_is_the_retailers_own_signature_for_that_site_record_and_number"),
    ("a link's number is ASCII digits", C, "not (parts[1].isascii() and parts[1].isdigit())", "not parts[1].isdigit()",
     R + "test_r1_a_link_is_the_retailers_own_signature_for_that_site_record_and_number"),
    ("a link made again stops the old one", S, 'ksc.num(s.get("number")) != number or ', "",
     T + "test_l3_make_link_again_stops_the_old_link_within_its_keep"),
    ("a screen whose stations or store changed is refused", S, ' or s.get("made_for") != ksc.made_for(s)', "",
     T + "test_g2_a_screen_whose_store_or_stations_changed_is_refused"),
    ("made_for covers the kind", C, '[screen.get("kind") or "", screen.get("store") or "",', '[screen.get("store") or "",',
     R + "test_r2_a_link_is_made_for_the_screens_kind_store_and_stations"),
    ("a link's number is at least 1", C, "        if number < 1:\n            return None\n", "",
     R + "test_r1_a_link_is_the_retailers_own_signature_for_that_site_record_and_number"),
    ("a refused sold-out read leaves the tickets", S, "            except TenantError:         # the sold-out right missing",
     "            except ZeroDivisionError:   # the sold-out right missing", T + "test_s6_a_sold_out_read_the_shop_refuses_leaves_the_tickets_showing"),
    ("a refused sold-out read is kept refused", S, "            self._keep(self._sold, key, (str(e), e.code, e.kind))\n            raise", "            raise",
     T + "test_s6_a_sold_out_read_the_shop_refuses_leaves_the_tickets_showing"),
    ("an expo card leaves with its dishes", C, '        live = [t for t in ts if t["kind"] == "send" and t["state"] != "bumped"]',
     '        live = [t for t in ts if t["state"] != "bumped"]', R + "test_r6b_the_expo_card_leaves_with_its_dishes_and_times_its_oldest_open_one"),
    ("a busy board keeps its newest", C, "[-BOARD_MAX:]", "[:BOARD_MAX]", R + "test_r7b_a_busy_board_keeps_its_newest_tickets"),
    ("made_for covers the stations", C, '",".join(sorted(stations_of(screen)))', '""',
     R + "test_r2_a_link_is_made_for_the_screens_kind_store_and_stations"),
    ("a store with no row is closed", S, "        if not row:\n            raise _Answer(200, {\"state\": \"closed\"})",
     "        if False:\n            raise _Answer(200, {\"state\": \"closed\"})", T + "test_g3_a_store_with_no_row_answers_closed"),
    ("the shop's refusal says not set up", S, "            if e.kind in SET_UP or e.code in (401, 403):", "            if False:",
     T + "test_g4_the_shop_refusing_the_app_user_answers_not_set_up"),
    # the board
    ("a station screen shows only its stations", C, '    mine = [t for t in tickets if t["station"] in stations]',
     "    mine = list(tickets)", T + "test_b1_a_station_screen_shows_its_own_stations_at_its_own_store"),
    ("a choice is not counted as waiting", C, '            if ln["under"] is not None or not ln["item_code"]:',
     '            if not ln["item_code"]:', T + "test_b2_the_expo_groups_each_order_and_adds_up_what_waits"),
    ("a void cancels what waits", C, '        sign_ = 1 if t["kind"] == "send" else -1', "        sign_ = 1",
     R + "test_r5_what_waits_counts_dishes_not_ready_less_a_void"),
    ("a ready dish is not waiting", C, '        if t["kind"] == "send" and t["state"] not in ("new", "started"):',
     "        if False:", R + "test_r5_what_waits_counts_dishes_not_ready_less_a_void"),
    ("the board shows counter sales unless tables", C, ' or not (tables or sends[0]["source"] == "sale")', "",
     T + "test_b3_the_board_shows_call_numbers_only_counter_sales_by_default"),
    ("an order is ready only when every station is", C,
     '    return bool(sends) and all(t["state"] in ("ready", "bumped") for t in sends) and any(t["state"] == "ready" for t in sends)',
     '    return any(t["state"] == "ready" for t in sends)', R + "test_r6_an_order_is_ready_when_every_send_ticket_is_and_leaves_when_all_are_bumped"),
    ("the board carries no dish", S, '            view = ksc.board_view(tickets, bool(ksc.num(row.get("tables_on_board"))))',
     '            view = dict(ksc.board_view(tickets, bool(ksc.num(row.get("tables_on_board")))), tickets=tickets)',
     T + "test_b3_the_board_shows_call_numbers_only_counter_sales_by_default"),
    ("screens of one store share one read", S, "        if not fresh and kept and self.clock() - kept[0] < BOARD_KEEP_S:",
     "        if False:", T + "test_b4_screens_of_one_store_share_one_read_and_a_screen_reads_twenty_times_a_minute"),
    ("the sold-out list is kept", S, "        if kept and self.clock() - kept[0] < SOLD_KEEP_S:", "        if False:",
     T + "test_b4_screens_of_one_store_share_one_read_and_a_screen_reads_twenty_times_a_minute"),
    ("two retailers' boards are never shared", S, "        key = (site, store)\n        kept = self._boards.get(key)",
     "        key = store\n        kept = self._boards.get(key)", M + "ManyShops.test_the_boards_of_two_retailers_are_never_shared"),
    ("the accent is only a colour", C, ' and _COLOUR.fullmatch(row.get("accent") or "")', "",
     R + "test_r8_the_look_takes_only_a_colour_and_known_words"),
    ("red always after amber", C, "max(setting(row.get(\"late_min\"), LATE),", "min(setting(row.get(\"late_min\"), LATE),",
     R + "test_r8_the_look_takes_only_a_colour_and_known_words"),
    ("a ticket keeps only its fields", C, '    return {"kitchen_order": order, "ticket": n,', '    return {**t, "kitchen_order": order, "ticket": n,',
     R + "test_r3_a_ticket_keeps_only_the_doors_fields_of_their_kinds"),
    ("a ticket's state is the door's", C, ' or t.get("state") not in ("new", "started", "ready", "bumped")', "",
     R + "test_r3_a_ticket_keeps_only_the_doors_fields_of_their_kinds"),
    # moves
    ("a station moves only its own stations' tickets", C, '    if kind == KIND_STATION and ticket["station"] not in stations:',
     "    if False:", T + "test_m3_a_station_screen_never_moves_another_stations_or_another_stores_ticket"),
    ("a skip or a step back is refused", C, '    if NEXT.get(ticket["state"]) != state and ticket["state"] != state:',
     "    if False:", T + "test_m2_a_skip_or_a_step_back_is_refused_before_the_door"),
    ("the board moves nothing", C, "    if kind == KIND_BOARD:\n        return \"board\"", "    if False:\n        return \"board\"",
     R + "test_r7_who_may_move_what"),
    ("the expo only bumps", C, '    if kind == KIND_EXPO and state != "bumped":', "    if False:",
     T + "test_m4_the_board_moves_nothing_and_the_expo_only_bumps"),
    ("only the expo bumps an order", S, '        if whole and s["kind"] != ksc.KIND_EXPO:', "        if False:",
     T + "test_m4_the_board_moves_nothing_and_the_expo_only_bumps"),
    ("the expo bumps an order only when it is ready", S, '            if not cards or not cards[0]["bump"]:', "            if not cards:",
     T + "test_m5_the_expo_bumps_an_order_only_when_every_station_is_ready"),
    ("a move is judged on the board as it is", S, 'tickets, _ = self.board(door, site, s["store"], fresh=True)',
     'tickets, _ = self.board(door, site, s["store"])', T + "test_m2_a_skip_or_a_step_back_is_refused_before_the_door"),
    ("a move goes to the screen's own store", S, '                door.call("station_ticket_move", {"store": s["store"],',
     '                door.call("station_ticket_move", {"store": body.get("store") or s["store"],',
     T + "test_m1_a_cook_moves_a_ticket_one_step_at_a_time_and_a_double_tap_is_safe"),
    ("taps are spaced", S, "            if now - self._moved.get(key, -1e9) < MOVE_GAP_S:", "            if False:",
     T + "test_m6_a_flood_of_taps_reads_the_retailer_no_more"),
    ("the door's step refusal is said", S, '                if e.kind == "TicketStepError":\n                    return {"state": "refused", "why": "step"}',
     '                if False:\n                    return {"state": "refused", "why": "step"}', T + "test_m7_the_doors_refusal_is_said_and_the_board_read_again"),
    ("a move names a whole-number ticket", S, "not isinstance(number, int) or isinstance(number, bool) or ", "",
     T + "test_m8_a_move_names_a_real_ticket"),
    # sold out
    ("sold out marks the screen's own store", S, '"warehouse": s["store"], "sold_out": 1 if out else 0,',
     '"warehouse": body.get("warehouse") or s["store"], "sold_out": 1 if out else 0,',
     T + "test_s1_a_dish_on_the_board_is_marked_sold_out_at_the_screens_own_store_only"),
    ("sold out only for a listed dish", S, "        if code not in listed:", "        if False:",
     T + "test_s2_an_item_the_kitchen_has_not_seen_is_refused"),
    ("a station's list is its own stations' dishes", S,
     '        return [t for t in tickets if t["station"] in ksc.stations_of(s)] if s["kind"] == ksc.KIND_STATION else tickets',
     "        return tickets", T + "test_s5_a_station_screen_offers_only_its_own_stations_dishes"),
    ("an item already out is on the list", S, ' | {d["item_code"] for d in self.sold(door, site, s["store"])}', "",
     T + "test_s3_an_item_already_sold_out_can_be_cleared_though_no_ticket_names_it"),
    ("sold out follows the store's switch", S, ' or not ksc.num(row.get("sold_out_on")):\n            return {"state": "refused", "why": "off"}',
     ':\n            return {"state": "refused", "why": "off"}', T + "test_s4_sold_out_off_for_the_store_or_from_the_board_is_refused"),
    ("no sold-out list when the store says no", S, '        if kind != ksc.KIND_BOARD and ksc.num(row.get("sold_out_on")):',
     "        if kind != ksc.KIND_BOARD:", T + "test_s4_sold_out_off_for_the_store_or_from_the_board_is_refused"),
    ("only items out now are on the list", C, ' and r.get("sold_out") and not r.get("available"):', ":",
     R + "test_r9_the_sold_out_list_is_the_boards_dishes_and_what_is_already_out"),
    # the page and every call
    ("the page's script comes from the service only", S, "script-src 'self';", "script-src 'self' 'unsafe-inline';",
     T + "test_e1_the_page_is_served_with_a_strict_policy_and_the_kits_files"),
    ("the page is never framed", S, " frame-ancestors 'none'", "", T + "test_e1_the_page_is_served_with_a_strict_policy_and_the_kits_files"),
    ("a large call is refused", S, "            if len(raw) > ksc.PAGE_BODY_MAX:", "            if False:",
     T + "test_e2_a_large_or_shapeless_call_is_refused"),
    # the size and the fit (fit.js, page.js)
    ("only the four size steps are taken from the device", FIT, "    if (SIZES.indexOf(chosen) >= 0) return chosen;",
     "    if (chosen) return chosen;", FR + "test_p1_a_screen_takes_the_cooks_size_then_the_stores_then_standard"),
    ("A- and A+ stop at the ends", FIT, "Math.max(0, Math.min(SIZES.length - 1, i))", "i",
     FR + "test_p2_a_minus_and_a_plus_stop_at_the_ends"),
    ("a page always holds one ticket", FIT, "for (var i = 1; i < bottoms.length; i++)", "for (var i = 0; i < bottoms.length; i++)",
     FR + "test_p3_a_page_ends_before_the_first_ticket_that_passes_the_bottom_and_holds_at_least_one"),
    ("the page asked for, not always the last", FIT, "if (starts.length - 1 >= want || end >= count) break;",
     "if (end >= count) break;", FR + "test_p4_pages_cover_every_ticket_in_order_and_stop_at_the_last"),
    ("a folded ticket keeps its first dish", FIT, "hide < heights.length - 1", "hide < heights.length",
     FR + "test_p5_a_tall_ticket_folds_its_last_dishes_and_keeps_the_first"),
    ("the store's default size is used", PAGE, "var v = window.kscFit.size(chosen, last && last.look && last.look.size)",
     'var v = window.kscFit.size(chosen, "standard")', PR + "test_q1_the_store_default_then_the_cooks_choice_kept_on_this_device"),
    ("a blocked device store does not stop the page", PAGE,
     '  try { chosen = window.localStorage.getItem(SIZE_KEY) || ""; } catch (e) { chosen = ""; }',
     '  chosen = window.localStorage.getItem(SIZE_KEY) || "";', PR + "test_q2_a_blocked_device_store_still_opens_and_sizes_the_screen"),
    ("a blocked device store does not stop A+", PAGE,
     "    try { window.localStorage.setItem(SIZE_KEY, chosen); } catch (e) { /* not kept on this device: this visit only */ }",
     "    window.localStorage.setItem(SIZE_KEY, chosen);", PR + "test_q2_a_blocked_device_store_still_opens_and_sizes_the_screen"),
    ("only a success takes a held refusal down", PAGE, ' && (a.state === "moved" || a.state === "set")', "",
     PR + "test_q3_a_tap_with_no_answer_does_not_take_down_a_held_refusal"),
    ("the retailer's words sit in <bdi>, never dir=auto", PAGE,
     "      if (own) e.appendChild(bdi(text));\n      else e.textContent = String(text);",
     '      e.textContent = String(text);\n      if (own) e.setAttribute("dir", "auto");',
     PR + "test_q4_the_retailers_words_are_isolated_and_nothing_is_dir_auto"),
    ("the store's size is one of the four", C, '"size": SIZES.get(row.get("slip_size") or "", "standard")',
     '"size": row.get("slip_size") or "standard"', R + "test_r8_the_look_takes_only_a_colour_and_known_words"),
    ("the store's size is read", S, '"tables_on_board",\n              "slip_size"]', '"tables_on_board"]',
     T + "test_b5_the_store_row_sets_the_look"),
    ("a kept sold-out answer is the shop's own", S, "                raise TenantError(*kept[1])   #",
     '                raise TenantError("item_availability -> refused (kept)", 403)   #',
     T + "test_s7_a_sold_out_read_that_timed_out_is_kept_as_a_timeout_not_a_refusal"),
    ("the first dish's choices fold when it alone is too tall", PAGE,
     "    while (tall(slip) > cap + 0.5 && choices < first.length - 1) first[first.length - ++choices].hidden = true;",
     "    choices = 0;", PF + "test_f1_a_dish_with_too_many_choices_folds_its_choices_and_keeps_bump"),
    ("a ticket one dish too tall scrolls", PAGE, '      slip.classList.add("is-tall"); slip.style.maxBlockSize = cap + "px";',
     "      cap = cap;", PF + "test_f2_a_single_dish_taller_than_the_board_scrolls_its_ticket"),
    ("a void station is never folded on the expo", PAGE,
     '      if (ul.parentNode && ul.parentNode.classList.contains("ksc-part") && ul.parentNode.classList.contains("is-void")) return;\n',
     "", PF + "test_f3_the_expo_never_folds_a_void_and_shows_again_what_fits"),
    ("what fits again is shown again", PAGE, "      if (tall(slip) > cap + 0.5) { fold(hide); break; }\n      hide--;",
     "      fold(hide); break;", PF + "test_f3b_a_folded_station_heading_frees_room_that_is_used_again"),
    ("only the page's tickets are shown", PAGE, "    slips.forEach(function (sl, i) { sl.hidden = i < shown.from || i >= shown.end; });",
     "    slips.forEach(function (sl) { sl.hidden = false; });", PF + "test_f4_whole_tickets_paged_in_order_and_none_left_out"),
    ("still to make shows whole dishes and a count", PAGE, "      dishes[dishes.length - 1 - hide++].hidden = true;", "      hide++;",
     PF + "test_f5_still_to_make_shows_whole_dishes_and_counts_the_rest"),
    ("a void says so in the whole-ticket dialog", PAGE,
     '      if (t.kind === "void") box.appendChild(withIcon("p", "ksc-void", "cross", w("void")));', "",
     PF + "test_f6_a_void_reads_as_one_in_the_whole_ticket_dialog"),
    ("a ticket nothing can fold still scrolls", PAGE, "    if (tall(slip) > cap + 0.5) {      // still too tall",
     "    if (!hide && !choices) { btn.hidden = true; return; }\n    if (tall(slip) > cap + 0.5) {      // still too tall",
     PF + "test_f2b_an_expo_void_too_tall_to_fold_scrolls_so_bump_order_stays_in_reach"),
    ("the board's +N is measured with its own text", PAGE,
     "      while (tag.getBoundingClientRect().bottom > limit && hide < nums.length) {", "      while (false) {",
     PF + "test_f7_the_board_counts_the_numbers_that_still_do_not_fit"),
    ("a ticket moved under the finger holds taps", PAGE,
     "    if (!cookPaged && left.some(function (k) { return !bumped[k]; })) shiftedAt = performance.now();", "",
     PF + "test_f8_a_ticket_moved_under_the_finger_holds_taps_a_moment"),
    ("the cook's own bump leaving holds nothing", PAGE, "return !bumped[k];", "return true;",
     PF + "test_f8b_the_cooks_own_bump_leaving_holds_nothing"),
    ("Arabic's dual", PAGE, '    if (lang === "ar" && n === 2) return w(one + "2");\n', "",
     PF + "test_f9_arabic_counts_take_their_dual_and_eleven_and_over_forms"),
    ("Arabic's hundreds", PAGE, "n > 2 && h < 3) return", "n > 2 && h < 1) return", PF + "test_f9_arabic_counts_take_their_dual_and_eleven_and_over_forms"),
    ("Arabic's eleven and over", PAGE, 'if (lang === "ar" && h >= 11)', 'if (lang === "ar" && n >= 11)',
     PF + "test_f9_arabic_counts_take_their_dual_and_eleven_and_over_forms"),
    ("a refused Bump is not the cook's", PAGE, '        delete bumped[key.replace', '        void bumped[key.replace',
     PF + "test_f8e_a_refused_bump_is_not_the_cooks_and_its_later_removal_holds"),
    ("a scrolling ticket keeps its parts' height", "service/page.css", ".ksc-slip.is-tall > * { flex-shrink: 0; }",
     ".ksc-slip.is-tall > * { }", PF + "test_f2c_a_scrolling_ticket_keeps_its_parts_height_so_every_line_shows"),
    ("a scrolling ticket folds nothing", PAGE, "      fold(0); hide = 0; choices = 0;", "      hide = hide;",
     PF + "test_f2d_a_ticket_that_scrolls_anyway_unfolds_what_was_folded"),
    ("the cook's own paging holds nothing", PAGE, "if (!cookPaged && left.some", "if (left.some",
     PF + "test_f8c_the_cooks_own_paging_holds_nothing"),
    ("only a bump the cook made is exempt", PAGE, '    if (extra.state === "bumped" || extra.order) bumped[',
     '    if (true) bumped[', PF + "test_f8d_a_ticket_the_cook_only_started_leaving_by_another_screen_holds"),
    ("every served file is in the hosted package", "app.json", '  "samples/s59_kitchen_screen/service/fit.js",\n', "",
     T + "test_e3_every_file_the_service_serves_is_in_the_hosted_package"),
    ("back on the network, read at once", PAGE, '  window.addEventListener("online", function () { readNow(); });', "",
     PF + "test_f10_a_screen_back_on_the_network_catches_up_on_its_next_read"),
    ("a late ticket elsewhere turns the pager red", PAGE, "      return s.classList.contains(\"is-late\") ||", "      return false &&",
     PF + "test_f11_a_late_ticket_on_another_page_turns_the_page_button_red"),
    ("back to the first page after a minute", PAGE, "if (want && performance.now() - touchedAt > PAGE_BACK_MS) want = 0;", "",
     PF + "test_f12_a_minute_after_the_last_touch_the_screen_goes_back_to_the_first_page"),
    ("a tap not applied says so", PAGE, '    else if ((a.state === "unavailable" || a.state === "not_set_up") && performance.now() >= noteUntil) {',
     '    else if (false) {', PF + "test_f13_a_tap_that_was_not_applied_says_so"),
    ("a failed read is tried again by itself", PAGE, "        stale(); schedule(RETRY_MS);", "        stale();", PF + "test_f10_a_screen_back_on_the_network_catches_up_on_its_next_read"),
    ("the cook's page stays inside the minute", PAGE, "performance.now() - touchedAt > PAGE_BACK_MS", "performance.now() - touchedAt > 0",
     PF + "test_f12_a_minute_after_the_last_touch_the_screen_goes_back_to_the_first_page"),
    ("a failing read leaves a tap's word", PAGE, '        if (!goodAt) note("unavailable");', '        note(goodAt ? "" : "unavailable");',
     PF + "test_f13_a_tap_that_was_not_applied_says_so"),
    ("a tap not applied gives the button back", PAGE, "        btn.disabled = false;\n", "",
     PF + "test_f13_a_tap_that_was_not_applied_says_so"),
    ("a tap refused for a right says so", PAGE, '(a.state === "unavailable" || a.state === "not_set_up")', '(a.state === "unavailable")',
     PF + "test_f13b_a_tap_refused_for_a_missing_right_says_so"),
    # the live service (HOSP-K1c)
    ("a line admits only a valid link, by the service's own check", LS, "            site, _door, s, _row = self.svc.opened(body)",
     '            site, s = body.get("s"), {"store": ""}', L + "LiveTest.test_v2_a_forged_or_replaced_link_opens_no_line_and_no_socket"),
    ("a notice reaches its own store's lines only", LS, "if store is None or ln.store == store]", "]",
     L + "LiveTest.test_v1_a_screens_line_hears_its_own_stores_notice_and_not_another_stores"),
    ("a line is read only by the screens' page", LS, '"Access-Control-Allow-Origin": origin, "Vary": "Origin", "Connection"',
     '"Access-Control-Allow-Origin": "*", "Vary": "Origin", "Connection"',
     L + "LiveTest.test_v1_a_screens_line_hears_its_own_stores_notice_and_not_another_stores"),
    ("a dropped socket says the line is down", LS, '            up = what == "signed in"', "            up = True",
     L + "LiveTest.test_v4_a_dropped_socket_says_so_then_comes_back_and_every_screen_reads"),
    ("after a reconnect every screen reads", LS, "            if up:                      # notices sent while",
     "            if False:                   # notices sent while",
     L + "LiveTest.test_v4_a_dropped_socket_says_so_then_comes_back_and_every_screen_reads"),
    ("a site's own name is learned", LS, "                if name:\n                    self.names[site] = name",
     "                if False:\n                    self.names[site] = name",
     L + "LiveTest.test_v5_a_site_named_apart_from_its_address_is_reached_by_its_own_name"),
    ("a key a site echoes never reaches a log line", SS, "Lost(_short(self.scrub(str(why))) or", "Lost(_short(str(why)) or",
     L + "LiveTest.test_v6_no_key_or_secret_reaches_a_log_line_and_a_wrong_key_is_refused"),
    ("a line ends and is checked again", LS, "                    if left <= 0:", "                    if left <= -1e9:",
     L + "LiveTest.test_v7_a_line_ends_with_again_and_the_socket_closes_after_the_last_line"),
    ("a socket lingers a minute after its last line", LS, 'now - e["idle_since"] >= LINGER_S', "True",
     L + "LiveTest.test_v7_a_line_ends_with_again_and_the_socket_closes_after_the_last_line"),
    ("one retailer's lines are bounded", LS, " or len(mine) >= SITE_STREAMS_MAX:", ":",
     L + "LiveTest.test_v8_too_many_lines_are_refused_busy_and_the_page_falls_back"),
    ("a notice of another event is not passed on", SS, "event[0] == EVENT and ", "",
     L + "SocketTest.test_k1_a_notice_of_another_event_or_shape_is_not_passed_on"),
    ("pings are answered", SS, '            if packet == "2":\n                self.send("3")', '            if packet == "2":\n                pass',
     L + "SocketTest.test_k3_pings_are_answered_and_the_edges_cookie_is_sent_back"),
    ("the page reaches the live service alone", S, "connect = \"'self'\" + (\" \" + self.live if self.live else \"\")",
     'connect = "*"', T + "test_e4_the_page_may_reach_the_live_service_and_nothing_else"),
    ("the live address is an origin, never a path", S, ' or parts.path not in ("", "/")', "",
     T + "test_e4_the_page_may_reach_the_live_service_and_nothing_else"),
    ("a parked or refused line leaves the 3-second reads", PAGE, "        if (!r.ok || !r.body || !r.body.getReader) { end(); return; }",
     "        if (!r.body || !r.body.getReader) { end(); return; }",
     PL + "test_l2_a_parked_or_refused_live_service_leaves_the_three_second_reads_and_says_nothing"),
    ("a notice reads the board at once", PAGE, '      } else if (name === "read" && liveOn) {\n        readNow();',
     '      } else if (name === "read" && liveOn) {\n        void 0;',
     PL + "test_l1_a_notice_on_the_live_line_reads_the_board_at_once_and_the_pace_slows_while_it_is_up"),
    ("a read from a line not up is not used", PAGE, 'name === "read" && liveOn', 'name === "read"',
     PL + "test_l4_a_line_not_yet_up_is_heard_but_reads_stay_at_three_seconds"),
    ("the slower pace only while the line is up", PAGE, "schedule(liveOn ? LIVE_READ_MS : READ_MS);", "schedule(LIVE_READ_MS);",
     PL + "test_l5_no_live_service_named_opens_no_line"),
    ("a line that ends puts the 3-second reads back", PAGE, "    liveOn = false; liveStop = null;", "    liveStop = null;",
     PL + "test_l3_a_line_that_ends_puts_the_three_second_reads_back"),
    # KSCSOLDNAME
    ("a sold-out dish is named by its record", S, "            value = ksc.with_names(value, named)", "            value = value",
     T + "test_s8_a_dish_sold_out_that_no_ticket_names_is_shown_by_its_name"),
    ("the page shows a sold-out dish's name", PAGE, "item_name: d.item_name || d.item_code }", "item_name: d.item_code }",
     PL + "test_l6_a_sold_out_dish_no_ticket_names_shows_its_name"),
    ("a names read refused leaves the codes", S, "            except TenantError:         # the names are a nicety",
     "            except KeyError:            # the names are a nicety",
     T + "test_s9_a_names_read_the_shop_refuses_leaves_the_codes_showing"),
    # the manifest
    ("only the app writes a link's number", "manifest.json", '"insert_after": "link_section",\n   "in_list_view": 1,\n   "write_roles": [\n    "PP KSC Integration",',
     '"insert_after": "link_section",\n   "in_list_view": 1,\n   "write_roles": [\n    "PP KSC Manager",', F + "test_m1_what_makes_a_link_work_only_the_app_writes"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s59-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", ".env.local"))
        for sub in ("tools/manifest", "tools/app_template", "tools/contracts", "contracts"):
            shutil.copytree(os.path.join(kit, sub), os.path.join(tmp, "r", sub), ignore=shutil.ignore_patterns("__pycache__"))
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.join(dest, path)
        src = open(f).read()
        if src.count(anchor) != 1:
            return "BROKEN", f"anchor found {src.count(anchor)} times"
        open(f, "w").write(src.replace(anchor, mutant))
        if f.endswith(".py"):
            py_compile.compile(f, doraise=True)
        elif f.endswith(".js") and shutil.which("node"):
            subprocess.run(["node", "--check", f], check=True, capture_output=True, timeout=60)
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
