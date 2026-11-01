#!/usr/bin/env python3
"""S37's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``), copied: a defect there is a defect here.

    python3 samples/s37_age_check/tests/canaries.py      # exit 0 only when every canary is RED
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
    # the rules
    ("a group's age covers the groups below it", "agecheck.py", "if age and lft <= g[0] and g[1] <= rgt]", "if age and lft == g[0]]",
     R + "Ages.test_a_groups_age_covers_the_groups_below_it"),
    ("the nearest group wins", "agecheck.py", "return max(above)[1] if above else 0", "return min(above)[1] if above else 0",
     R + "Ages.test_the_nearest_group_with_an_age_wins"),
    ("an item's own age wins", "agecheck.py", "    if own:\n        return own\n", "",
     R + "Ages.test_an_items_own_age_wins_over_its_group"),
    ("an age is a whole age", "agecheck.py", "and v == int(v) and 0 < v <= 120", "and v > 0",
     R + "Ages.test_an_age_that_is_not_a_whole_age_is_no_age"),
    ("the scan shows the date of birth", "agecheck.py", "Born on or before {d.day} {d:%b %Y}. {ask}", "{ask}",
     R + "Scan.test_a_restricted_item_shows_the_date_and_records_the_check"),
    ("the scan records the check on the sale", "agecheck.py",
     '"sale_attributes": [{"sale_attribute": f"{prefix} {CHECKED}", "attribute_value": checked_value(age)}]}', '}',
     R + "Scan.test_a_restricted_item_shows_the_date_and_records_the_check"),
    ("the shop's look-under policy only above the age", "agecheck.py", "if look > age else", "if look else",
     R + "Scan.test_see_their_id_when_the_shop_has_no_policy_or_it_is_not_above_the_age"),
    ("no age is a plain allow", "agecheck.py", "    if not age:\n        return {\"verdict\": \"allow\"}\n", "",
     R + "Scan.test_no_age_is_allow_with_nothing_shown"),
    ("29 February is the 28th", "agecheck.py", "return today.replace(year=today.year - age, day=28)",
     "return today.replace(year=today.year - age, day=27)",
     R + "Scan.test_born_by_is_the_same_day_that_many_years_ago_and_29_february_is_the_28th"),
    ("the shop's own day", "agecheck.py", "(t + datetime.timedelta(hours=hours)).date()", "t.date()",
     R + "Scan.test_today_is_the_shops_own_day"),
    ("a line above the recorded check is refused", "agecheck.py", 'line["qty_milli"] > 0 and age > checked]',
     'line["qty_milli"] > 0 and age > checked and False]', R + "Check.test_a_restricted_line_with_no_check_is_refused_naming_it_and_the_age"),
    ("a check at the age allows", "agecheck.py", 'line["qty_milli"] > 0 and age > checked]', 'line["qty_milli"] > 0 and age >= checked]',
     R + "Check.test_a_recorded_check_at_the_age_or_above_allows"),
    ("the highest age is named", "agecheck.py", "    age = max(a for a, _ in short)\n", "    age = short[0][0]\n",
     R + "Check.test_a_lower_check_is_refused_naming_the_highest_age_needed"),
    ("a return's taken-back line is not judged", "agecheck.py", 'if line["qty_milli"] > 0 and age > checked]', 'if age > checked]',
     R + "Check.test_a_return_is_judged_only_for_what_it_sells"),
    ("only this app's sale detail counts", "agecheck.py", 'if a["name"] == want), "")', 'if a["name"].endswith(CHECKED)), "")',
     R + "Check.test_another_apps_sale_detail_is_not_this_apps_check"),
    ("a check that is not a number is none", "agecheck.py", 'return _age(int(m.group(1))) if m else 0', 'return _age(int(m.group(1))) if m else 18',
     R + "Check.test_a_check_that_is_not_a_number_counts_as_none"),
    ("only a whole age alone is a check (a date typed in is none)", "agecheck.py", "m = re.fullmatch(", "m = re.search(",
     R + "Check.test_only_a_whole_age_alone_is_a_check"),
    ("an age above 120 is none", "agecheck.py", "return _age(int(m.group(1))) if m else 0", "return int(m.group(1)) if m else 0",
     R + "Check.test_only_a_whole_age_alone_is_a_check"),
    ("a variant takes its template's age", "agecheck.py", '    own = own or (items.get(template) or (0, ""))[0]\n', "",
     R + "Ages.test_a_variant_with_no_age_of_its_own_takes_its_templates"),
    ("the refusal's item is cut to fit", "agecheck.py", 'plain(line["item_code"], 24)', 'plain(line["item_code"], 40)',
     R + "Check.test_every_refusal_is_plain_and_at_most_140"),
    ("a lower ask never lowers the remembered age", "agecheck.py", "(now, max(age, kept))", "(now, age)",
     R + "Asked.test_a_sale_asked_about_at_an_age_is_covered_for_that_age_and_below"),
    ("a remembered age is per sale", "agecheck.py", "hit = self.seen.get((shop, sale_ref))", "hit = next(iter(self.seen.values()), None)",
     R + "Asked.test_another_sale_or_shop_is_not_covered"),
    ("no reference is never remembered", "agecheck.py", "        if not sale_ref:\n            return\n", "",
     R + "Asked.test_a_sale_with_no_reference_is_never_remembered"),
    ("the asks are forgotten after four hours", "agecheck.py", "and self.clock() - hit[0] < ASKED_TTL and", "and",
     R + "Asked.test_it_is_forgotten_after_four_hours_and_an_old_age_does_not_carry_over"),
    ("sentences are plain", "agecheck.py", '.replace("<", "").replace(">", "")', "", R + "Scan.test_every_sentence_is_plain_and_at_most_140"),
    ("the shape is checked first", "agecheck.py", 'and _number(x.get("qty_milli")) for x in lines):', "for x in lines):",
     R + "Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the scan is the scan event only", "agecheck.py", 'or ctx.get("event") != "scan":', ":",
     R + "Context.test_a_scan_is_read_only_for_the_scan_event"),
    # the service
    ("an asked sale is not asked again", "service/app.py", 'if not age or self.asked.covered(name, ref, age):', "if not age:",
     S + "OneShop.test_a_sale_asked_about_is_not_asked_again_for_that_age_or_below"),
    ("the scan's ask is remembered", "service/app.py", "        self.asked.remember(name, ref, age)\n", "",
     S + "OneShop.test_a_sale_asked_about_is_not_asked_again_for_that_age_or_below"),
    ("a refund reads nothing", "service/app.py", "        if not agecheck.sells(ctx):\n", "        if False:\n",
     S + "OneShop.test_a_refund_is_allowed_without_reading_anything"),
    ("the signature is checked", "service/app.py", "if not secrets or all(agecheck.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_each_route_takes_only_its_own_secret"),
    ("each route takes its own secret", "service/app.py", 'return "-", [self.secrets[route_key]], self.shop',
     'return "-", list(self.secrets.values()), self.shop', S + "OneShop.test_each_route_takes_only_its_own_secret"),
    ("an old timestamp is refused", "agecheck.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("the shop's day comes from its hours", "service/app.py", "agecheck.today_at(settings[\"hours\"], self.now())",
     "agecheck.today_at(0, self.now())", S + "OneShop.test_the_shops_hours_decide_the_date_shown"),
    ("an item the shop does not return is unreadable", "service/app.py", "            if set(missing) - set(read):\n",
     "            if False:\n", S + "OneShop.test_an_item_the_shop_does_not_return_is_a_503"),
    ("the settings and groups are kept a minute", "service/app.py", 'if not (hit and hit[1] == key and now - hit[0] < KEPT_TTL):',
     "if True:", S + "OneShop.test_the_settings_groups_and_items_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the service reads a variant's template", "service/app.py", "        for _step in range(2):", "        for _step in range(1):",
     S + "OneShop.test_a_variant_is_judged_by_its_templates_age_read_in_a_second_step"),
    ("only the items not kept are read", "service/app.py", "        missing = sorted(set(codes) - set(items))\n",
     "        missing = sorted(set(codes))\n", S + "OneShop.test_the_settings_groups_and_items_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the ages are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_ages_and_the_asks_are_kept_per_shop"),
    ("a new key reads the shop again", "service/app.py", 'if not (hit and hit[1] == key and now - hit[0] < KEPT_TTL):',
     "if not (hit and now - hit[0] < KEPT_TTL):", S + "ManyShops.test_a_new_key_reads_the_shop_again"),
    ("a new key reads the items again", "service/app.py", "        mine = (name, key)  ", "        mine = (name, '')  ",
     S + "ManyShops.test_a_new_key_reads_the_shop_again"),
    ("a missing settings record is none, not an error", "service/app.py", "            if missing and e.code == 404:\n",
     "            if False:\n", S + "ShopApi.test_reads_the_settings_record_with_the_token_and_none_when_missing"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("every item group is read, not one page", "service/app.py", 'f"{p}_min_age"]), "limit_page_length": 0}), list)',
     'f"{p}_min_age"]), "limit_page_length": 20}), list)', S + "ShopApi.test_reads_every_item_group_with_the_apps_age"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'notice'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_scan_and_check_either_body_form_and_a_refusal"),
    # the manifest
    ("the integration role carries the prefix", "manifest.json", '"role": "PP AGE Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_settings"),
    ("the check lets the sale go on when down", "manifest.json",
     '"timeout_seconds": 3, "down_answer": "allow_and_flag"', '"timeout_seconds": 3, "down_answer": "refuse"',
     M + "test_two_services_switched_off_that_let_the_sale_go_on_when_down"),
    ("the scan filters on the app's age field", "manifest.json", '"item_field": "pp_age_min_age"', '"item_field": "stock_uom"',
     M + "test_the_scan_asks_about_the_items_the_app_gives_an_age"),
    # the test call (X-iVendNext-Test: 1, tools/app_template/service/testcall.py): checked as a real call, never the handler
    ("a test call never reaches the handler", "service/app.py", "if testcall.is_test(headers):", "if False:",
     "test_service.TestCall.test_a_signed_test_call_is_answered_ok_without_the_handler"),
    ("a test call is answered only where its route matches", "service/app.py",
     '        if path not in ROUTES:\n            return 404, {"error": "not found"}\n',
     '        if testcall.is_test(headers):\n            return testcall.answer("x")\n        if path not in ROUTES:\n            return 404, {"error": "not found"}\n',
     "test_service.TestCall.test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s37-canary-")
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
