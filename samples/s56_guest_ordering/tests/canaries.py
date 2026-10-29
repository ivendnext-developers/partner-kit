#!/usr/bin/env python3
"""S56's canaries: each test that guards a retailer's secret, a code's signature and its number, which check an order
joins, one order per table at a time, the door's keys, the menu's limits, a guest's choices, or the page's own rules
must go RED when that check is removed. For each mutation this copies the sample (and the kit folders it uses) to a
temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the
anchor must match exactly once, and the mutant must compile), runs the test again, and reports RED (the test caught
it) or GREEN (a dead test). The runner is S45's.

    python3 samples/s56_guest_ordering/tests/canaries.py      # exit 0 only when every canary is RED
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
S, C, Q = "service/app.py", "gor.py", "qr.py"

CANARIES = [
    # the press and the retailer
    ("the press's signature is checked", S, "        if not secrets or all(gor.verify(ts, sig, raw, s.decode()) for s in secrets):",
     "        if not secrets:", T + "test_c1_an_unsigned_or_wrongly_signed_press_is_refused"),
    ("a press stamped long ago is refused", C, " or abs((now or time.time()) - int(ts)) > SKEW_S:", ":",
     T + "test_c1_an_unsigned_or_wrongly_signed_press_is_refused"),
    ("a press names its own record type", C, ' or rec.get("doctype") != doctype', "",
     T + "test_c6_a_press_on_another_record_type_is_refused_before_anything_is_read"),
    ("the code's secret is the code button's", S, 'secrets = shops.secrets_for(record, f"{self.app}:sub:{SUB}")',
     'secrets = [v.encode() for k, v in (record or {}).get("secrets", {}).items() if not k.startswith("user:")]',
     M + "ManyShops.test_another_retailers_code_is_refused"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a redirect is never followed", S, "host\n        return None\n", "host\n        return super().redirect_request(*a, **k)\n",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a record name is one path segment", S, '"/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))',
     'urllib.parse.quote(path, safe="/")', M + "ShopApi.test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed"),
    # Make code
    ("Make code raises the number", S, "            number = gor.num(c.get(\"number\")) + 1",
     "            number = gor.num(c.get(\"number\")) or 1", T + "test_c3_make_code_again_stops_the_old_card"),
    ("a table must be on the store's floor", S, "                if gor.place_of(floors[c[\"store\"]], c[\"place\"]) is None:",
     "                if False:", T + "test_c4_a_table_not_on_the_floor_and_a_nameless_kiosk_get_no_code"),
    ("Make code keeps the record's own modified", S, '"made_for": gor.made_for(c), "modified": c.get("modified")}',
     '"made_for": gor.made_for(c)}', T + "test_c5_a_code_changed_a_moment_ago_is_not_overwritten"),
    # the code's link
    ("the link's signature is checked", C, "    return (record, number) if any(hmac.compare_digest(sign(s, site, record, number), sig) for s in secrets) else None",
     "    return (record, number)", T + "test_g1_a_forged_or_edited_link_is_refused_before_the_shop_is_read"),
    ("the signature covers the number", C, 'f"gor1|{site}|{record}|{number}"', 'f"gor1|{site}|{record}"',
     R + "test_r1_a_code_is_the_retailers_own_signature_for_that_record_and_number"),
    ("the signature covers the site", C, 'f"gor1|{site}|{record}|{number}"', 'f"gor1|{record}|{number}"',
     R + "test_r1_a_code_is_the_retailers_own_signature_for_that_record_and_number"),
    ("a code made again stops the old card", S, 'gor.num(c.get("number")) != number or ', "",
     T + "test_c3_make_code_again_stops_the_old_card"),
    ("a code whose table changed is refused", S, ' or c.get("made_for") != gor.made_for(c)', "",
     T + "test_g2_a_code_whose_table_changed_since_it_was_made_is_refused"),
    ("the store's switch is read", S, ' or not gor.num(row.get("tables_on" if table else "kiosk_on"))', "",
     T + "test_g3_the_stores_switch_off_answers_ask_staff"),
    # which check an order joins
    ("two bills at a table are refused", S, "                if len(checks) > 1:", "                if False:",
     T + "test_o3_two_bills_at_the_table_are_refused_and_nothing_is_written"),
    ("an open bill is added to, never a second opened", S,
     '                check = checks[0]["check"] if checks else self.open(', '                check = self.open(',
     T + "test_o2_one_bill_at_the_table_gets_the_lines"),
    ("the door's add key is made from the page's", S, '"key": gor.door_key(key, "add")})', '"key": gor.door_key(key + str(self.now()), "add")})',
     T + "test_o4_a_retry_after_a_lost_answer_opens_and_adds_once"),
    ("the door's open key is made from the page's", S, '"key": gor.door_key(key, "open"), "source"',
     '"key": gor.door_key(key + str(self.now()), "open"), "source"',
     T + "test_k1_a_kiosk_order_opens_a_tab_named_by_its_code_and_a_retry_opens_none"),
    ("one order a code at a time", S, "            if self._spaced.get(name, 0) > now - gor.SPACING_S:", "            if False:",
     T + "test_o5_one_order_a_table_every_fifteen_seconds"),
    ("one order a code across every copy", S, "            if not self.store.claim(name, now, gor.SPACING_S):", "            if False:",
     M + "ManyShops.test_one_order_a_code_across_every_copy_of_the_function"),
    ("a retry onto a moved bill is said", S, '            if e.kind == "CheckRequestError":', '            if False:',
     T + "test_o6_a_retry_of_lines_since_moved_says_it_was_sent_once"),
    # review wave 1's folds
    ("a bill being paid takes no guest order", S, '                if checks and checks[0].get("status") == "paying":',
     "                if False:", T + "test_o10_a_bill_being_paid_takes_no_guest_order"),
    ("the claim is the table's, not the card's", S,
     "        where = f\"{c.get('store')}|{c.get('place')}\" if c.get(\"kind\") == gor.KIND_TABLE else c.get(\"name\")",
     "        where = c.get(\"name\")", T + "test_o11_one_order_a_table_even_with_two_cards_on_it"),
    ("the kiosk code is keyed with the retailer's secret", C,
     '    n = int.from_bytes(hmac.new(secret, f"gor1|kiosk|{key}".encode(), hashlib.sha256).digest()[:8], "big")',
     '    n = int.from_bytes(hashlib.sha256(f"gor1|kiosk|{key}".encode()).digest()[:8], "big")',
     R + "test_r4_the_kiosk_code_is_five_letters_that_cannot_be_misread_nor_chosen_by_the_guest"),
    ("a gift card is not on the menu", S, ', ["custom_is_gift_card", "=", 0]], limit=gor.MENU_MAX)', '], limit=gor.MENU_MAX)',
     T + "test_m4_a_gift_card_in_a_menu_group_is_not_on_the_menu"),
    ("a dish named by anything but text is refused", C, ' if isinstance(ln.get("item_code"), str) else None', "",
     T + "test_o12_a_body_the_page_never_sends_is_refused_and_nothing_is_written"),
    ("a choice named by anything but text is refused", C, ' or not all(isinstance(p, str) for p in picked)', "",
     T + "test_o12_a_body_the_page_never_sends_is_refused_and_nothing_is_written"),
    ("a refused open is ask staff, never sent", S,
     "the floor read\n            if not e.refused:\n                raise\n            return 200, closed",
     "the floor read\n            raise", T + "test_o13_a_table_switched_off_after_the_floor_read_is_ask_staff_not_sent"),
    ("a verified code is kept, not read again", S, "        if kept and self.clock() - kept[0] < CODE_KEEP_S:", "        if False:",
     T + "test_m6_a_flood_of_calls_on_one_code_reads_the_retailer_once_a_copy"),
    ("a menu the budget cut is read again soon", S, "        late = any(v is LATE for v in prices.values())", "        late = False",
     T + "test_m5_a_menu_the_time_budget_cut_prices_only_what_it_missed_soon_after"),
    ("a refused code is kept too, not read again", S, "                self._codes[key] = (self.clock(), c, row)",
     "                if c:\n                    self._codes[key] = (self.clock(), c, row)",
     T + "test_m7_a_flood_on_a_replaced_card_reads_the_retailer_once_a_copy"),
    ("a late menu prices only what it missed", S, "                  **self.prices(door, reg, [c for c in need if c not in known], t0)}",
     "                  **self.prices(door, reg, need, t0)}",
     T + "test_m5_a_menu_the_time_budget_cut_prices_only_what_it_missed_soon_after"),
    ("a crafted token is refused, not a fault", C, "    except ValueError:                  # a digit int() refuses",
     "    except KeyError:                  # a digit int() refuses",
     R + "test_r1_a_code_is_the_retailers_own_signature_for_that_record_and_number"),
    ("a link too long for a QR code is said", S, "            except ValueError:\n                problems.append(f\"{name}: its link",
     "            except KeyError:\n                problems.append(f\"{name}: its link", T + "test_c7_a_link_too_long_for_a_qr_code_is_said_and_nothing_written"),
    ("the card prints the QR only for its own record", "manifest.json", "{% if made %}", "{% if doc.qr %}",
     F + "test_m9_the_card_prints_the_qr_only_for_the_record_and_table_it_was_made_for"),
    # the order's checks
    ("a dish must be on the menu", C, "        if d is None:\n            raise Refused(\"Something", "        if False:\n            raise Refused(\"Something",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("the store's quantity limit", C, " or not 1 <= qty <= most_qty:", ":", T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("whole quantities only", C, "        if isinstance(qty, bool) or not isinstance(qty, int) or", "        if",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("the store's line limit", C, "    if len(raw) > most_lines:", "    if False:",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("a choice must be the dish's own", C, "            if code not in own:", "            if False:",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("a group's least picks", C, '            if n < g["min"]:', "            if False:",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("a group's most picks", C, '            if g["max"] and n > g["max"]:', "            if False:",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("each choice once", C, "        if len(set(picked)) != len(picked):", "        if False:",
     T + "test_o8_the_order_is_checked_against_the_menu_and_the_stores_limits"),
    ("a dish sold only as a choice is not on the menu", C, ' or r.get("custom_mpos_option_only")', "",
     T + "test_m1_the_menu_is_the_registers_groups_dishes_choices_and_prices"),
    ("a choice's price is its row's amount", C, '    base = money(row.get("price")) if row.get("price_type") == "Amount" else money(list_rate)',
     "    base = money(list_rate)", R + "test_r5_a_choices_price_is_the_rows_amount_else_the_list_price_less_its_discount"),
    ("a register with no menu groups has no menu", S, "        if not groups:\n", "        if False:\n",
     T + "test_m2_a_register_with_no_menu_groups_answers_ask_staff"),
    ("the page's key must be a fresh value", C, "    return v if isinstance(v, str) and _KEY.fullmatch(v) else None", "    return v or None",
     T + "test_o9_a_key_that_is_not_a_fresh_value_is_refused"),
    ("a note is one line of text", C, ' if unicodedata.category(c)[0] not in ("C", "Z") or c == " " else " "', "",
     R + "test_r6_a_note_is_one_line_of_text_at_most_eighty_characters"),
    ("the guest's lines carry the course", C, '        line = {"item_code": d["code"], "qty": qty, "course": course}',
     '        line = {"item_code": d["code"], "qty": qty}', T + "test_o1_no_bill_at_the_table_opens_one_and_adds_the_lines_unsent_under_the_course"),
    # the kiosk
    ("a kiosk tab carries its party of one", S, '        req.update({"place": place} if place else {"label": label, "covers": 1})',
     '        req.update({"place": place} if place else {"label": label})',
     T + "test_k1_a_kiosk_order_opens_a_tab_named_by_its_code_and_a_retry_opens_none"),
    ("the kiosk code has no misreadable letter", C, 'KIOSK_LETTERS = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"',
     'KIOSK_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"', R + "test_r4_the_kiosk_code_is_five_letters_that_cannot_be_misread_nor_chosen_by_the_guest"),
    # the page and the manifest
    ("the page allows no inline script", S, "script-src 'self'; ", "script-src 'self' 'unsafe-inline'; ",
     T + "test_e1_the_page_is_served_with_its_own_rules"),
    ("a guest's call has its size limit", S, "            if len(raw) > gor.PAGE_BODY_MAX:", "            if False:",
     T + "test_e2_a_page_call_over_its_size_is_refused"),
    ("the QR's error correction", Q, "    rem = data\n    for _ in range(10):", "    rem = data ^ 1\n    for _ in range(10):",
     R + "test_q2_the_grids_the_framework_drew_the_same"),
    ("the QR's codeword interleave", Q, "            if i != short_len - ecc_len or j >= short:", "            if True:",
     R + "test_q2_the_grids_the_framework_drew_the_same"),
    ("only the app writes the number", "manifest.json", '"in_list_view": 1,\n   "write_roles": [\n    "PP GOR Integration",',
     '"in_list_view": 1,\n   "write_roles": [\n    "PP GOR Manager", "PP GOR Integration",',
     F + "test_m1_what_makes_a_code_work_only_the_app_writes"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s56-canary-")
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
