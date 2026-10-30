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
S, C = "service/app.py", "ksc.py"

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
