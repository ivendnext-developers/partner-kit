#!/usr/bin/env python3
"""S38's canaries: each test that guards a shop's secret, its key, a price the shop typed, a concurrent edit, the step
chosen, the rounding or the service's words must go RED when that check is removed. For each mutation this copies the sample (and the kit folders it
uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN), applies ONE change
(the anchor must match exactly once, and the mutant must compile), runs the test again, and reports RED (the test caught
it) or GREEN (a dead test). The runner is S16's.

    python3 samples/s38_expiry_markdown/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, S, R = "test_service.ServiceTest.", "test_many_shops.", "service/app.py", "markdown.py"

CANARIES = [
    ("the signature is checked", S, "        if not secrets or all(markdown.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", M + "ManyShops.test_another_shops_secret_an_unknown_site_and_no_site_are_refused"),
    ("each shop's own user key", S, 'if k.startswith("user:") and k != "user:Administrator")', 'if ":" in k)',
     M + "ManyShops.test_each_shop_is_written_with_its_own_key_under_the_librarys_prefix"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a press before the shop's key arrives is answered in words", S, "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n",
     "", M + "ManyShops.test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403):", "            if False:",
     T + "test_s15_the_apps_user_refused_by_the_shop_is_said_in_words"),
    ("a price the shop typed is never changed", R, "    if any(not own(r) for r in lot_rows):", "    if False:",
     T + "test_s8_a_price_the_shop_typed_for_a_lot_is_never_changed"),
    ("the sweep removes only the app's own", S, "[r for r in old if isinstance(r, dict) and markdown.own(r)]",
     "[r for r in old if isinstance(r, dict)]", T + "test_s11_the_apps_expired_prices_are_swept_and_the_shops_own_never"),
    ("the app's own is its prefix and a colon", R, '    return isinstance(row.get("note"), str) and row["note"].startswith(PREFIX + ": ")',
     '    return isinstance(row.get("note"), str) and row["note"].startswith(PREFIX)',
     T + "test_s8_a_price_the_shop_typed_for_a_lot_is_never_changed"),
    ("an update names the row as it was read", R, '            writes.append(("update", r, dict(want, valid_from=today.isoformat(), modified=r.get("modified"))))',
     '            writes.append(("update", r, dict(want, valid_from=today.isoformat())))', T + "test_s4_a_lot_that_reaches_its_last_step_is_changed_with_the_row_as_read"),
    ("a stale write is never written over", S, "            if e.kind == STALE or (w[0] == \"delete\" and e.code == 404):",
     "            if w[0] == \"delete\" and e.code == 404:", T + "test_s10_an_edit_saved_between_the_read_and_the_write_is_never_written_over"),
    ("the deepest step reached wins", R, "    return min(reached)[1] if reached else None", "    return max(reached)[1] if reached else None",
     T + "test_s2_a_lot_in_its_last_step_takes_the_last_percent"),
    ("a lot past its date is never marked down", R, "    if days_left < 0:\n        return None\n", "",
     T + "test_s7b_a_lot_past_its_date_is_never_marked_down"),
    ("the nearest group wins", R, "    return max(above)[1] if above else []", "    return min(above)[1] if above else []",
     T + "test_s6_the_nearest_group_with_steps_wins"),
    ("rounded down, never up", R, "rounding=ROUND_FLOOR)", "rounding=ROUND_HALF_UP)",
     T + "test_s1_a_lot_in_its_first_step_gets_its_own_price_until_its_expiry_date"),
    ("the currency's own digits", R, '    return DIGITS.get(number_format, 2) if isinstance(number_format, str) else 2', "    return 2",
     T + "test_s13_the_currencys_own_digits_are_the_grain"),
    ("an unreadable currency writes nothing", S, '.get("number_format"))\n        except TenantError as e:\n            if e.code == 404:\n                return _warning(bad_list(price_list))\n            raise',
     '.get("number_format"))\n        except TenantError as e:\n            exponent = 2', T + "test_s13b_a_currency_the_app_cannot_read_writes_nothing"),
    ("a lot's row older than the item's is moved", R, "        if older or any(r.get(f) != v for f, v in want.items()):",
     "        if any(r.get(f) != v for f, v in want.items()):", T + "test_s4b_a_newer_item_price_moves_the_lots_row_to_today"),
    ("a moved row takes today", R, '            writes.append(("update", r, dict(want, valid_from=today.isoformat(), modified=r.get("modified"))))',
     '            writes.append(("update", r, dict(want, modified=r.get("modified"))))', T + "test_s4b_a_newer_item_price_moves_the_lots_row_to_today"),
    ("a customer's own price is not the base", R, ' or not _blank(r.get("customer"))', "",
     T + "test_s1_a_lot_in_its_first_step_gets_its_own_price_until_its_expiry_date"),
    ("a price not valid today is not the base", R, "        if (frm and frm > today) or (upto and upto < today):\n            continue\n", "",
     T + "test_s1_a_lot_in_its_first_step_gets_its_own_price_until_its_expiry_date"),
    ("the price ends on the expiry date", R, '    upto, note = expiry.isoformat(), note_for(pct)', '    upto, note = None, note_for(pct)',
     T + "test_s1_a_lot_in_its_first_step_gets_its_own_price_until_its_expiry_date"),
    ("the sweep takes only expired rows", S, ', ["valid_upto", "<", today.isoformat()]])', "])",
     T + "test_s11_the_apps_expired_prices_are_swept_and_the_shops_own_never"),
    ("another lot's price is never the base", R, ' or not _blank(r.get("batch_no"))', "",
     T + "test_s1b_another_lots_markdown_is_never_the_base"),
    ("a supplier's price is never the base", R, '                or not _blank(r.get("supplier")) or not', "                or not",
     T + "test_s1_a_lot_in_its_first_step_gets_its_own_price_until_its_expiry_date"),
    ("a disabled lot takes the markdown off", R, ' or lot.get("disabled")', "",
     T + "test_s7c_a_disabled_lot_has_the_apps_price_taken_off"),
    ("out of stock takes the markdown off", R, " or (isinstance(qty, (int, float)) and qty <= 0)", "",
     T + "test_s7_a_lot_past_its_date_out_of_stock_or_out_of_every_step_has_the_apps_price_taken_off"),
    ("a press stops in time", S, "            if done and self.clock() - t0 > BUDGET_S:\n                break\n", "",
     T + "test_s12_a_press_stops_in_time_and_says_how_many_are_left"),
    ("the shop's day, not UTC", R, "    return (t + datetime.timedelta(hours=hours or 0)).date()", "    return t.date()",
     T + "test_s16_the_shops_day_decides_the_days_left"),
    ("only a selling list that is on", S, "        if not pl.get(\"selling\") or not pl.get(\"enabled\"):", "        if False:",
     T + "test_s14_no_settings_or_a_list_the_tills_do_not_sell_from_is_said_in_words"),
    ("one to 100 lots, all lots", R, '    if not 1 <= len(recs) <= MOST_LOTS:', "    if False:",
     T + "test_a_press_must_name_one_to_100_lots"),
    ("a long body is cut", R, '    return text if len(text) <= most else text[: most - 1] + "…"', "    return text",
     T + "test_every_answer_fits_the_answers_limit"),
    ("the prefix names the fields", R, '    DAYS, PCT = (f"{p}_days_1", f"{p}_days_2"), (f"{p}_pct_1", f"{p}_pct_2")', "    pass",
     M + "Prefix.test_the_fields_follow_the_prefix_and_the_manifest_names_them"),
    ("a redirect is not followed", S, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a record name is one path segment", S, 'urllib.parse.quote(p, safe="")', "urllib.parse.quote(p)",
     M + "ShopApi.test_a_record_name_is_one_path_segment"),
    ("a cut answer is an unknown outcome", S, "(OSError, ValueError, http.client.HTTPException) as e:     # OSError",
     "(OSError, ValueError) as e:     # OSError", M + "ShopApi.test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash"),
    ("the function checks the signature too", S, "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'ok': 1}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     M + "AsAFunction.test_health_a_signed_press_either_body_form_and_a_refusal"),
    # the test call (X-iVendNext-Test: 1, tools/app_template/service/testcall.py): checked as a real call, never the handler
    ("a test call never reaches the handler", "service/app.py", "if testcall.is_test(headers):", "if False:",
     "test_service.TestCall.test_a_signed_test_call_is_answered_ok_without_the_handler"),
    ("a test call is answered only where its route matches", "service/app.py",
     '        if path == "/press/markdown":\n',
     '        if testcall.is_test(headers):\n            return testcall.answer("x")\n        if path == "/press/markdown":\n',
     "test_service.TestCall.test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s38-canary-")
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
