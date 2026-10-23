#!/usr/bin/env python3
"""S48's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S47's
(``samples/s48_customer_code_check/tests/canaries.py``, from S23's), copied: a defect there is a defect here.

    python3 samples/s48_customer_code_check/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M, V = "test_rules.Select.", "test_service.", "test_manifest.ManifestTest.", "test_rules.Verify."

CANARIES = [
    ("a rule that asks gets a code", "codecheck.py", '    if not found or not found[1]["ask"] or recent:\n', '    if True:\n',
     R + "test_a_group_whose_rule_asks_gets_a_code_named_by_its_last_two_digits"),
    ("never ask lets a group off", "codecheck.py", '    if not found or not found[1]["ask"] or recent:\n', '    if not found or recent:\n',
     R + "test_never_ask_lets_a_group_below_off_the_code"),
    ("a right code in the last half hour is not asked again", "codecheck.py", ' or not found[1]["ask"] or recent:', ' or not found[1]["ask"]:',
     R + "test_a_right_code_in_the_last_half_hour_is_not_asked_again"),
    ("the prompt names the last two digits", "codecheck.py", "ending {digits(phone)[-2:]}.", "ending soon.",
     R + "test_a_group_whose_rule_asks_gets_a_code_named_by_its_last_two_digits"),
    ("a group takes the rule above it", "codecheck.py", "        if g in rules:\n            return g, rules[g]\n    return None",
     "        pass\n    return None", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("a group's own rule replaces the one above", "codecheck.py", "    if group in rules:\n        return group, rules[group]\n",
     "", R + "test_never_ask_lets_a_group_below_off_the_code"),
    ("a customer with no group takes the outermost rule", "codecheck.py",
     "above = [g for g, (l, r) in tree.items() if not any(l2 < l and r < r2 for l2, r2 in tree.values())]", "above = []",
     R + "test_a_customer_with_no_group_takes_the_outermost_rule"),
    ("no mobile number takes the customer off", "codecheck.py", '        if rule["let_on"]:\n', '        if True:\n',
     R + "test_no_mobile_number_takes_the_customer_off_where_the_rule_says"),
    ("no mobile number lets them on where the rule says", "codecheck.py", '        if rule["let_on"]:\n', '        if False:\n',
     R + "test_no_mobile_number_lets_the_customer_on_where_the_rule_says"),
    ("a short number is no number", "codecheck.py", "    if len(digits(who[\"phone\"])) < MOBILE_MIN:", "    if not who[\"phone\"].strip():",
     R + "test_no_mobile_number_takes_the_customer_off_where_the_rule_says"),
    ("a value the form never writes asks", "codecheck.py", '"ask": _text(r.get("ask")) != NEVER', '"ask": _text(r.get("ask")) == ASK',
     R + "test_a_value_the_form_never_writes_errs_on_the_side_of_the_code"),
    ("a group the tree does not know is unreadable", "codecheck.py",
     "    if group and group not in tree and group not in rules and rules:\n", "    if False:\n",
     R + "test_a_group_the_tree_does_not_know_is_unreadable_while_the_shop_has_rules"),
    ("sentences are plain", "codecheck.py", '.replace("<", "").replace(">", "")', "",
     R + "test_every_sentence_is_plain_and_at_most_140"),
    ("empty words fall back", "codecheck.py", "    if own.strip(MARKS):\n", "    if True:\n",
     R + "test_words_that_come_out_empty_fall_back_to_the_apps_own"),
    ("a wrong code is refused", "codecheck.py", 'if not hmac.compare_digest(record["code"].encode(), ctx["code"].encode()):',
     "if False:", V + "test_a_wrong_code_is_refused_in_words"),
    ("a used code has ended", "codecheck.py", 'record.get("status") != SENT or ', "", V + "test_a_used_an_old_or_a_missing_code_has_ended"),
    ("an old code has ended", "codecheck.py", "not 0 <= now - record[\"sent_at\"] <= CODE_TTL_S", "False",
     V + "test_a_used_an_old_or_a_missing_code_has_ended"),
    ("ten minutes is still good", "codecheck.py", "<= CODE_TTL_S:", "< CODE_TTL_S:", V + "test_ten_minutes_is_still_good"),
    ("a cleared code never matches", "codecheck.py", '        or not record["code"] or ', "        or ",
     V + "test_a_used_an_old_or_a_missing_code_has_ended"),
    ("a code is six digits from a secure source", "codecheck.py", 'return f"{secrets.randbelow(10 ** LENGTH):0{LENGTH}d}"',
     'return f"{secrets.randbelow(10 ** LENGTH)}"', "test_rules.Codes.test_a_code_is_six_digits_from_a_secure_source"),
    ("a verify carries a code of letters and digits", "codecheck.py", "code.isascii() and code.isalnum() and ", "",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("only a select or a verify is answered", "codecheck.py", '    if ctx.get("event") != "customer_select":\n', '    if False:\n',
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the signature is checked", "service/app.py", "if not secrets or all(codecheck.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_capture_takes_only_its_own_secret"),
    ("an old timestamp is refused", "codecheck.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("a long timestamp is refused, never parsed", "codecheck.py", "ts.isdigit() and len(ts) <= 12)", "ts.isdigit())",
     "test_rules.Signature.test_the_signature_and_the_time_are_checked"),
    ("the code record is written before the challenge", "service/app.py",
     "            self.api.create(shop[\"url\"], shop[\"key\"], self.prefix, codecheck.code_record(ctx, codecheck.new_code(), now))\n",
     "            pass\n", S + "OneShop.test_a_customer_whose_rule_asks_gets_a_challenge_after_the_code_record_is_written"),
    ("a code the shop cannot save is a 503", "service/app.py", "            self.api.create(", "            (lambda *a: None)(",
     S + "OneShop.test_a_code_the_shop_cannot_save_is_a_503_so_the_down_answer_applies"),
    ("a right code is spent", "service/app.py", '            self.api.used(shop["url"], shop["key"], self.prefix, ctx["challenge_id"], now)\n',
     "            pass\n", S + "OneShop.test_the_code_the_customer_reads_out_lets_them_on_once"),
    ("the last right code is read for this cashier, customer and POS Profile", "service/app.py",
     '["operator", "=", ctx["operator"]], ', "", S + "ShopApi.test_reads_this_cashiers_last_right_code_for_this_customer_here"),
    ("the half hour counts from now", "service/app.py", "ctx, now - codecheck.REUSE_S)", "ctx, 0)",
     S + "OneShop.test_a_right_code_in_the_last_half_hour_is_read_for_this_cashier_customer_and_pos_profile"),
    ("a missing code record is none", "service/app.py", "            if missing_ok and e.code == 404:\n                return None\n", "",
     S + "ShopApi.test_a_missing_code_record_is_none_and_a_refused_one_unreadable"),
    ("the rules are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_rules_are_kept_per_shop"),
    ("a new key reads the rules again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if hit and now - hit[0] < RULES_TTL:", S + "ManyShops.test_a_new_key_reads_the_rules_again"),
    ("the rules are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if False:", S + "OneShop.test_the_rules_and_the_tree_are_kept_a_minute_the_last_code_is_read_every_pick"),
    ("the tree down is a 503", "service/app.py", '                groups = pool.submit(self.api.tree, shop["url"], shop["key"])',
     "                groups = pool.submit(lambda: [])", S + "OneShop.test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules"),
    ("a shop without its key is a 503", "service/app.py",
     "raise ShopUnreadable(\"the shop has not handed over its integration user's key\")\n        now = int(self.wall())\n        kept",
     "pass\n        now = int(self.wall())\n        kept",
     S + "ManyShops.test_a_shop_without_its_integration_key_is_a_503"),
    ("codes that are not records are a 503", "service/app.py", "        if not isinstance(recent, list):\n", "        if False:\n",
     S + "OneShop.test_codes_that_are_not_records_are_a_503"),
    ("a refused key is named apart", "service/app.py", "raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)",
     "raise (ShopUnreadable)", S + "ShopApi.test_a_refused_key_is_named_apart_from_an_outage"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("only switched-on rules are read", "service/app.py", 'codecheck.RULE_FIELDS, [["enabled", "=", 1]])',
     "codecheck.RULE_FIELDS, [])", S + "ShopApi.test_reads_every_switched_on_rule_with_the_token"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'allow'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_select_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP CCC Integration",\n     "read": 1,\n     "write": 0',
     '"role": "PP Integration",\n     "read": 1,\n     "write": 0', M + "test_the_integration_role_only_reads_the_rules"),
    ("no other role reads a code", "manifest.json", '"permissions": [\n    {\n     "role": "PP CCC Integration",\n     "read": 1,\n     "write": 1',
     '"permissions": [\n    {\n     "role": "System Manager",\n     "read": 1,\n     "write": 0, "create": 0, "delete": 0, "report": 0, "export": 0, "share": 0, "print": 0, "email": 0\n    },\n    {\n     "role": "PP CCC Integration",\n     "read": 1,\n     "write": 1',
     M + "test_the_code_records_are_the_integration_roles_alone"),
    ("the capture keeps the customer on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_select_capture_switched_off_that_keeps_the_customer_on_when_down"),
    ("the capture answers the customer select", "manifest.json", '"event": "customer_select"', '"event": "customer_add"',
     M + "test_one_select_capture_switched_off_that_keeps_the_customer_on_when_down"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s48-canary-")
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
