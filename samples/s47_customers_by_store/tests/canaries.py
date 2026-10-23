#!/usr/bin/env python3
"""S47's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``, by S32 and S46), copied: a defect there is a defect here.

    python3 samples/s47_customers_by_store/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M = "test_rules.Rules.", "test_service.", "test_manifest.ManifestTest."

CANARIES = [
    ("a place the rule names keeps the customer on", "storerules.py",
     "    if allowed_here(rule[\"places\"], ctx[\"store\"], ctx[\"pos_profile\"]):\n", "    if False:\n",
     R + "test_a_store_the_rule_names_keeps_the_customer_on"),
    ("a place elsewhere takes the customer off", "storerules.py",
     "    if allowed_here(rule[\"places\"], ctx[\"store\"], ctx[\"pos_profile\"]):\n", "    if True:\n",
     R + "test_a_store_the_rule_does_not_name_takes_the_customer_off_in_words"),
    ("both sides of a place must match", "storerules.py", "(not s or s == store) and (not p or p == pos_profile)",
     "(not s or s == store) or (not p or p == pos_profile)", R + "test_a_place_with_both_sides_needs_that_pos_profile_at_that_store"),
    ("a POS Profile alone is any store", "storerules.py", "(not s or s == store) and", "(s == store) and",
     R + "test_a_pos_profile_alone_is_that_pos_profile_at_any_store"),
    ("a group takes the rule above it", "storerules.py", "        if g in rules:\n            return g, rules[g]\n    return None",
     "        pass\n    return None", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("the nearest rule up the tree wins", "storerules.py", "key=lambda g: tree[g][0], reverse=True)", "key=lambda g: tree[g][0])",
     R + "test_the_nearest_rule_wins_over_one_further_up"),
    ("a group above holds the group's span", "storerules.py", "above = [g for g, (l, r) in tree.items() if l < lft and rgt < r]",
     "above = [g for g, (l, r) in tree.items() if l < lft]", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("a group's own rule replaces the one above", "storerules.py", "    if group in rules:\n        return group, rules[group]\n",
     "", R + "test_a_groups_own_rule_replaces_the_rule_above_it"),
    ("a customer with no group takes the outermost rule", "storerules.py",
     "above = [g for g, (l, r) in tree.items() if not any(l2 < l and r < r2 for l2, r2 in tree.values())]", "above = []",
     R + "test_a_customer_with_no_group_takes_the_outermost_rule"),
    ("a rule that names nowhere stops its group", "storerules.py", "    return {\"verdict\": \"refuse\", \"reason\": _reason(group, rule)}",
     "    return {\"verdict\": \"refuse\", \"reason\": _reason(group, rule)} if rule[\"places\"] else {\"verdict\": \"allow\"}",
     R + "test_a_rule_that_names_nowhere_stops_its_group_everywhere"),
    ("a blank place is no place", "storerules.py", "        if any(place):\n", "        if True:\n",
     "test_rules.RulesOf.test_a_place_with_both_sides_blank_is_no_place"),
    ("every place row of a rule counts", "storerules.py", "            rule[\"places\"].add(place)", "            pass",
     "test_rules.RulesOf.test_one_rule_per_group_with_every_place_row"),
    ("sentences are plain", "storerules.py", ".replace(\"<\", \"\").replace(\">\", \"\")", "",
     R + "test_every_sentence_is_plain_and_at_most_140"),
    ("the refusal's budget keeps the list whole", "storerules.py", "buy only at {plain(where, 73)}", "buy only at {plain(where, 60)}",
     R + "test_the_refusal_keeps_a_long_group_and_place_list_whole_within_its_budget"),
    ("empty words fall back", "storerules.py", "    if own.strip(MARKS):\n", "    if True:\n",
     R + "test_words_that_come_out_empty_fall_back_to_the_apps_own"),
    ("the marks are kept", "storerules.py", "if ch.isprintable() or ch in MARKS", "if ch.isprintable()",
     R + "test_the_marks_arabic_and_persian_text_carry_are_kept"),
    ("only a customer select is answered", "storerules.py", "or ctx.get(\"event\") != \"customer_select\":", ":",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the customer's group must be text", "storerules.py",
     "    if not isinstance(who, dict) or not isinstance(who.get(\"customer_group\"), str):", "    if False:",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the signature is checked", "service/app.py", "if not secrets or all(storerules.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_select_takes_only_its_own_secret"),
    ("an old timestamp is refused", "storerules.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("the rules are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_rules_are_kept_per_shop"),
    ("a new key reads the rules again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if hit and now - hit[0] < RULES_TTL:", S + "ManyShops.test_a_new_key_reads_the_rules_again"),
    ("the rules are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if False:", S + "OneShop.test_the_rules_and_the_tree_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the tree is read with the rules", "service/app.py", "storerules.tree_of(groups.result())", "storerules.tree_of([])",
     S + "OneShop.test_a_group_takes_the_rule_above_it_from_the_shops_tree"),
    ("the tree down is a 503", "service/app.py", "            groups = pool.submit(self.api.tree, shop[\"url\"], shop[\"key\"])",
     "            groups = pool.submit(lambda: [])", S + "OneShop.test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules"),
    ("a shop without its key is a 503", "service/app.py", "        if not shop:\n            raise ShopUnreadable",
     "        if False:\n            raise ShopUnreadable", S + "ManyShops.test_a_shop_without_its_integration_key_is_a_503"),
    ("a refusal by the shop is unreadable", "service/app.py",
     'raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)(f"the shop answered {e.code}") from None',
     "return {}", S + "ShopApi.test_a_refusal_an_error_or_a_404_is_unreadable"),
    ("a refused key is named apart", "service/app.py", "raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)",
     "raise (ShopUnreadable)", S + "ShopApi.test_a_refused_key_is_named_apart_from_an_outage"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("only switched-on rules are read", "service/app.py", 'storerules.RULE_FIELDS, [["enabled", "=", 1]])',
     "storerules.RULE_FIELDS, [])", S + "ShopApi.test_reads_every_switched_on_rule_with_its_places_and_the_token"),
    ("every switched-on rule is read, not one page", "service/app.py", '"limit_page_length": 0})', '"limit_page_length": 20})',
     S + "ShopApi.test_reads_every_switched_on_rule_with_its_places_and_the_token"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'refuse', 'reason': 'x'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_select_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP CBS Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_rules"),
    ("the capture keeps the customer on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_select_capture_switched_off_that_keeps_the_customer_on_when_down"),
    ("the capture answers the customer select", "manifest.json", '"event": "customer_select"', '"event": "customer_add"',
     M + "test_one_select_capture_switched_off_that_keeps_the_customer_on_when_down"),
    ("the places table is required", "manifest.json", '"options": "PP CBS Rule Place",\n     "reqd": 1,', '"options": "PP CBS Rule Place",\n     "reqd": 0,',
     M + "test_one_rule_per_group_named_by_it_with_the_fields_the_service_reads"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s47-canary-")
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
