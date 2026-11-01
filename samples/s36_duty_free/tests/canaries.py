#!/usr/bin/env python3
"""S36's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``), copied: a defect there is a defect here.

    python3 samples/s36_duty_free/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M = "test_rules.", "test_service.", "test_manifest.ManifestTest."

CANARIES = [
    ("no pass is refused", "service/app.py", "        if not pass_text:\n", "        if False:\n",
     S + "OneShop.test_no_pass_is_refused_without_reading_the_shop"),
    ("the pass's problem refuses", "service/app.py", "        if problem:\n", "        if False:\n",
     S + "OneShop.test_a_pass_from_elsewhere_or_another_day_is_refused"),
    ("a pass needs format M", "dutyfree.py", 'or t[0] != "M" or', "or", R + "Pass.test_what_is_not_a_boarding_pass_reads_nothing"),
    ("each leg steps past its variable part", "dutyfree.py", "        pos += LEG + n\n", "        pos += LEG\n",
     R + "Pass.test_every_leg_is_read_past_each_legs_variable_part"),
    ("the day is 1 to 366", "dutyfree.py", "and 1 <= int(day) <= 366", "", R + "Pass.test_what_is_not_a_boarding_pass_reads_nothing"),
    ("the airport is checked", "dutyfree.py", "here = [x for x in found if not airports or x[side] in airports]",
     "here = found", R + "Judge.test_a_flight_from_another_airport_is_refused_naming_both"),
    ("an arrivals shop reads where the flight arrives", "dutyfree.py", 'side, airports = ("to" if settings["arriving"] else "from")',
     'side, airports = ("from")', R + "Judge.test_an_arrivals_shop_takes_a_flight_arriving_here_dated_today_or_the_two_days_before"),
    ("an arrivals shop takes a pass dated two days before", "dutyfree.py", 'steps = (0, -1, -2) if settings["arriving"]',
     'steps = (0, -1) if settings["arriving"]', R + "Judge.test_an_arrivals_shop_takes_a_flight_arriving_here_dated_today_or_the_two_days_before"),
    ("an arrivals shop has its own words for another day", "dutyfree.py",
     'return OTHER_DAY_ARRIVING if settings["arriving"] else OTHER_DAY', "return OTHER_DAY",
     R + "Judge.test_an_arrivals_shop_takes_a_flight_arriving_here_dated_today_or_the_two_days_before"),
    ("a mistyped airport is kept, never read as any", "dutyfree.py", '"airports": sorted({c.upper() for c in codes}),',
     '"airports": sorted({c.upper() for c in codes if len(c) == 3}),',
     R + "Settings.test_a_mistyped_airport_is_kept_so_it_refuses_by_name_never_reads_as_any"),
    ("the day is checked", "dutyfree.py", '    if any(x["day"] in days for x in here):\n', '    if True:\n',
     R + "Judge.test_another_days_flight_is_refused"),
    ("a departures shop also takes tomorrow's flight", "dutyfree.py", 'else (0, 1)', "else (0,)",
     R + "Judge.test_a_flight_from_the_shops_airport_today_or_tomorrow_passes"),
    ("the day crosses the new year", "dutyfree.py", "(today + datetime.timedelta(days=n)).timetuple().tm_yday",
     "((today + datetime.timedelta(days=n)) - datetime.date(2026, 1, 1)).days + 1",
     R + "Judge.test_the_day_crosses_the_new_year"),
    ("the airport's own day", "dutyfree.py", "(t + datetime.timedelta(hours=hours)).date()", "t.date()",
     R + "Pass.test_today_is_the_airports_own_day"),
    ("a group's allowance covers the groups below it", "dutyfree.py", "lft <= g[0] and g[1] <= rgt", "lft == g[0]",
     R + "Allowance.test_a_groups_allowance_covers_the_groups_below_it"),
    ("past the allowance is refused", "dutyfree.py", "if total > allowance + 1e-9:", "if False:",
     R + "Allowance.test_at_the_allowance_passes_and_past_it_is_refused_in_its_own_unit"),
    ("at the allowance is allowed", "dutyfree.py", "if total > allowance + 1e-9:", "if total >= allowance:",
     R + "Allowance.test_at_the_allowance_passes_and_past_it_is_refused_in_its_own_unit"),
    ("only the touched groups are judged", "dutyfree.py", "for g in sorted(set(touched)):", "for g in sorted(totals):",
     R + "Allowance.test_only_the_groups_this_sale_touches_are_judged"),
    ("sentences are plain", "dutyfree.py", '.replace("<", "").replace(">", "")', "",
     R + "Context.test_every_sentence_is_plain_and_at_most_140"),
    ("the shape is checked first", "dutyfree.py", 'and isinstance(x.get("uom"), str) and _number(x.get("qty_milli")) for x in lines):',
     'for x in lines):', R + "Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("a refund reads nothing", "service/app.py", "        if not dutyfree.sells(ctx):\n", "        if False:\n",
     S + "OneShop.test_a_refund_is_allowed_without_reading_anything"),
    ("each item counts its measure", "service/app.py", "or 1.0       # blank or 0", "and 1.0      # blank or 0",
     S + "OneShop.test_past_the_allowance_is_refused_counting_each_items_measure"),
    ("a line in another unit counts its stock units", "service/app.py", "                factor = next(", "                factor = 1 or next(",
     S + "OneShop.test_a_line_in_another_unit_counts_its_stock_units"),
    ("earlier sales count", "service/app.py", "        rows += [(r[\"item_group\"]", "        rows += [] and [(r[\"item_group\"]",
     S + "OneShop.test_the_passengers_earlier_sales_on_the_same_pass_count"),
    ("earlier sales are read only when the shop says so", "service/app.py", '                if settings["earlier"] else None', "",
     S + "OneShop.test_earlier_sales_are_not_read_when_the_shop_says_so"),
    ("an item the shop does not return is unreadable", "service/app.py", "            if set(codes) - set(items):\n", "            if False:\n",
     S + "OneShop.test_an_item_on_the_sale_the_shop_does_not_return_is_a_503"),
    ("the signature is checked", "service/app.py", "if not secrets or all(dutyfree.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_check_takes_only_its_own_secret"),
    ("an old timestamp is refused", "dutyfree.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("the settings are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_settings_are_kept_per_shop"),
    ("a new key reads the settings again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < KEPT_TTL:',
     "if hit and now - hit[0] < KEPT_TTL:", S + "ManyShops.test_a_new_key_reads_the_settings_again"),
    ("the settings are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < KEPT_TTL:',
     "if False:", S + "OneShop.test_the_settings_and_groups_are_read_with_the_apps_key_and_kept_a_minute"),
    ("a refused key refuses the sale in words", "service/app.py",
     'return 200, {"verdict": "refuse", "reason": KEY_REFUSED}', 'return 200, {"verdict": "allow"}',
     S + "OneShop.test_a_refused_key_refuses_the_sale_in_words"),
    ("401 and 403 are a refused key", "service/app.py", "raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)",
     "raise ShopUnreadable", S + "ShopApi.test_a_refusal_is_key_refused_and_an_error_is_unreadable"),
    ("a missing settings record is none, not an error", "service/app.py", "            if missing and e.code == 404:\n",
     "            if False:\n", S + "ShopApi.test_reads_the_settings_record_with_the_token_and_none_when_missing"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("the pass is matched as written", "service/app.py", 'if c in "%_\\\\" else c', "if False else c",
     S + "ShopApi.test_finds_earlier_sales_by_the_passs_first_60_characters_matched_as_written"),
    ("every item group is read, not one page", "service/app.py", 'f"{p}_unit"]), "limit_page_length": 0}), list)',
     'f"{p}_unit"]), "limit_page_length": 20}), list)', S + "ShopApi.test_reads_every_item_group_with_the_apps_two_fields"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'allow'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP DFA Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_settings"),
    ("the check lets the sale go on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_check_switched_off_that_lets_the_sale_go_on_when_down"),
    # the test call (X-iVendNext-Test: 1, tools/app_template/service/testcall.py): checked as a real call, never the handler
    ("a test call never reaches the handler", "service/app.py", "if testcall.is_test(headers):", "if False:",
     "test_service.TestCall.test_a_signed_test_call_is_answered_ok_without_the_handler"),
    ("a test call is answered only where its route matches", "service/app.py",
     '        if path != ROUTE:\n            return 404, {"error": "not found"}\n',
     '        if testcall.is_test(headers):\n            return testcall.answer("x")\n        if path != ROUTE:\n            return 404, {"error": "not found"}\n',
     "test_service.TestCall.test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s36-canary-")
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
