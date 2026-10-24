#!/usr/bin/env python3
"""S50's canaries: each test that guards a rule, a secret or a read of the retailer must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and a Python
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``, by S32 and S46), copied: a defect there is a defect here.

    python3 samples/s50_required_sale_details/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M, D = "test_rules.Rules.", "test_service.", "test_manifest.ManifestTest.", "details.py"

CANARIES = [
    ("a needed detail left empty refuses", D, "    if not gaps:\n        return {\"verdict\": \"allow\"}",
     "    if True:\n        return {\"verdict\": \"allow\"}", R + "test_a_needed_detail_left_empty_refuses_the_sale_naming_it"),
    ("a blank value counts as empty", D, 'if any(not ch.isspace() and ch not in MARKS + ZERO_WIDTH for ch in a.get("value") or "")',
     'if any(not ch.isspace() for ch in a.get("value") or "")',
     R + "test_a_blank_value_counts_as_empty"),
    ("only the rule's details are needed", D, "    return [d for d in rule[\"details\"] if d not in filled]",
     "    return [d for d in rule[\"details\"] if not filled]", R + "test_a_detail_the_rule_does_not_name_changes_nothing"),
    ("a rule holds only at its POS Profiles", D, '    if rule["profiles"] and ctx.get("pos_profile") not in rule["profiles"]:',
     "    if False:", R + "test_a_rule_holds_only_at_its_pos_profiles"),
    ("a group takes the rule above it", D, '        if g in rules:\n            return g, rules[g]\n    return None',
     "        pass\n    return None", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("the nearest rule up the tree wins", D, "key=lambda g: tree[g][0], reverse=True)", "key=lambda g: tree[g][0])",
     R + "test_the_nearest_rule_wins_and_replaces_the_one_above_it"),
    ("a group above holds the group's span", D, "above = [g for g, (l, r) in tree.items() if l < lft and rgt < r]",
     "above = [g for g, (l, r) in tree.items() if l < lft]", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("a customer with no group takes the outermost rule", D,
     "above = [g for g, (l, r) in tree.items() if not any(l2 < l and r < r2 for l2, r2 in tree.values())]", "above = []",
     R + "test_a_customer_with_no_group_takes_the_outermost_rule"),
    ("a refund is never judged", D, '    if ctx["stage"] != "sale":\n        return {"verdict": "allow"}',
     '    if False:\n        return {"verdict": "allow"}', R + "test_a_refund_or_an_exchanges_returned_lines_are_never_judged"),
    ("every detail row of a rule counts", D, '            rule["details"].append(detail)', "            pass",
     "test_rules.RulesOf.test_one_rule_per_group_with_every_detail_and_profile"),
    ("a detail is named once", D, 'if isinstance(detail, str) and detail and detail not in rule["details"]:',
     "if isinstance(detail, str) and detail:", "test_rules.RulesOf.test_a_detail_repeated_by_the_join_is_kept_once"),
    ("every profile row counts", D, '            rule["profiles"].add(profile)', "            pass",
     "test_rules.RulesOf.test_one_rule_per_group_with_every_detail_and_profile"),
    ("sentences are plain", D, '.replace("<", "").replace(">", "")', "", R + "test_every_sentence_is_plain_and_at_most_140"),
    ("the refusal's budget keeps 140", D, 'names = plain(", ".join(gaps), 52)', 'names = plain(", ".join(gaps), 60)',
     R + "test_every_sentence_is_plain_and_at_most_140"),
    ("empty words fall back", D, "    if own.strip(MARKS):\n", "    if True:\n",
     R + "test_words_that_come_out_empty_fall_back_to_the_apps_own"),
    ("the marks are kept", D, "if ch.isprintable() or ch in MARKS", "if ch.isprintable()",
     R + "test_the_marks_arabic_and_persian_text_carry_are_kept"),
    ("sale details must be a list of names and text", D,
     '    elif not isinstance(attrs, list) or not all(isinstance(a, dict) and isinstance(a.get("name"), str)',
     "    elif False and all(isinstance(a, dict) and isinstance(a.get(\"name\"), str)",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the signature is checked", "service/app.py", "if not secrets or all(details.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_check_takes_only_its_own_secret"),
    ("an old timestamp is refused", D, "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("a long timestamp is refused, never parsed", D, "ts.isdigit() and len(ts) <= 12)", "ts.isdigit())",
     "test_rules.Verify.test_the_signature_and_the_time_are_checked"),
    ("the rules are kept per retailer", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_rules_are_kept_per_retailer"),
    ("a new key reads the rules again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if hit and now - hit[0] < RULES_TTL:", S + "ManyShops.test_a_new_key_reads_the_rules_again"),
    ("the rules are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if False:", S + "OneShop.test_the_rules_and_the_tree_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the tree is read with the rules", "service/app.py", "details.tree_of(groups.result())", "details.tree_of([])",
     S + "OneShop.test_a_group_takes_the_rule_above_it_from_the_retailers_tree"),
    ("a refund reads nothing", "service/app.py", 'if ctx["stage"] != "sale":\n            return 200', 'if False:\n            return 200',
     S + "OneShop.test_a_refund_reads_nothing"),
    ("the tree down is a 503", "service/app.py", "            groups = pool.submit(self.api.tree, shop[\"url\"], shop[\"key\"])",
     "            groups = pool.submit(lambda: [])", S + "OneShop.test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules"),
    ("a retailer without its key is a 503", "service/app.py", "        if not shop:\n            raise ShopUnreadable",
     "        if False:\n            raise ShopUnreadable", S + "ManyShops.test_a_retailer_without_its_integration_key_is_a_503"),
    ("a refusal by the retailer is unreadable", "service/app.py",
     'raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)(f"the retailer answered {e.code}") from None',
     "return {}", S + "ShopApi.test_a_refusal_an_error_or_a_404_is_unreadable"),
    ("a refused key is named apart", "service/app.py", "raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)",
     "raise (ShopUnreadable)", S + "ShopApi.test_a_refused_key_is_named_apart_from_an_outage"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("only switched-on rules are read", "service/app.py", 'details.RULE_FIELDS, [["enabled", "=", 1]])',
     "details.RULE_FIELDS, [])", S + "ShopApi.test_reads_every_switched_on_rule_with_its_details_and_the_token"),
    ("every switched-on rule is read, not one page", "service/app.py", '"limit_page_length": 0})', '"limit_page_length": 20})',
     S + "ShopApi.test_reads_every_switched_on_rule_with_its_details_and_the_token"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'refuse', 'reason': 'x'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP RSD Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_rules"),
    ("the check lets the sale go on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_check_switched_off_that_lets_the_sale_go_on_when_down"),
    ("the details table is never required", "manifest.json", '"options": "PP RSD Rule Detail",', '"options": "PP RSD Rule Detail",\n   "reqd": 1,',
     M + "test_one_rule_per_group_named_by_it_with_the_fields_the_service_reads"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s50-canary-")
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
