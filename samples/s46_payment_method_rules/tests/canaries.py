#!/usr/bin/env python3
"""S46's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``, by S32), copied: a defect there is a defect here.

    python3 samples/s46_payment_method_rules/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("only these leaves out the others", "payrules.py", 'out = [t for t in offered if t not in rule["methods"] or t in short]',
     'out = [t for t in offered if t in rule["methods"] or t in short]', R + "test_only_these_leaves_out_every_other_offered_method"),
    ("every method but these leaves out the listed ones", "payrules.py",
     '        out = [t for t in offered if (t in rule["methods"] and t not in need) or t in short]', "        out = []", R + "test_every_method_but_these_leaves_out_the_listed_ones"),
    ("a group takes the rule above it", "payrules.py", '        if g in rules:\n            return g, rules[g]\n    return None',
     "        pass\n    return None", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("the nearest rule up the tree wins", "payrules.py", "key=lambda g: tree[g][0], reverse=True)", "key=lambda g: tree[g][0])",
     R + "test_the_nearest_rule_wins_over_one_further_up"),
    ("a group above holds the group's span", "payrules.py", "above = [g for g, (l, r) in tree.items() if l < lft and rgt < r]",
     "above = [g for g, (l, r) in tree.items() if l < lft]", R + "test_a_group_with_no_rule_takes_the_nearest_rule_above_it"),
    ("nothing left to pay with refuses", "payrules.py", "    if len(out) == len(offered):", "    if False:",
     R + "test_a_rule_that_leaves_out_every_offered_method_refuses_the_sale_in_words"),
    ("never a partial list past 20", "payrules.py", "    if len(out) > EXCLUDE_MAX:", "    if False:",
     R + "test_more_methods_to_leave_out_than_the_contract_carries_refuses"),
    ("a refund is never judged", "payrules.py", '    if ctx["stage"] != "sale":\n        return {"verdict": "allow"}',
     '    if False:\n        return {"verdict": "allow"}', R + "test_a_refund_or_an_exchange_is_never_judged"),
    ("a customer with no group takes the outermost rule", "payrules.py",
     "above = [g for g, (l, r) in tree.items() if not any(l2 < l and r < r2 for l2, r2 in tree.values())]", "above = []",
     R + "test_a_customer_with_no_group_takes_the_outermost_rule"),
    ("every method row of a rule counts", "payrules.py", '            rule["methods"].add(method)', "            pass",
     "test_rules.RulesOf.test_one_rule_per_group_with_every_method_row"),
    ("an unknown kind is left out", "payrules.py", "or kind not in (ONLY, BUT):", ":",
     "test_rules.RulesOf.test_a_row_without_a_group_or_with_an_unknown_kind_is_left_out"),
    ("sentences are plain", "payrules.py", '.replace("<", "").replace(">", "")', "",
     R + "test_every_sentence_is_plain_and_at_most_140"),
    ("offered_tenders must be a list of text", "payrules.py",
     "if not isinstance(offered, list) or not all(isinstance(t, str) for t in offered):", "if False:",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the signature is checked", "service/app.py", "if not secrets or all(payrules.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_check_takes_only_its_own_secret"),
    ("an old timestamp is refused", "payrules.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("a long timestamp is refused, never parsed", "payrules.py", "ts.isdigit() and len(ts) <= 12)", "ts.isdigit())",
     "test_rules.Verify.test_the_signature_and_the_time_are_checked"),
    ("the rules are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_rules_are_kept_per_shop"),
    ("a new key reads the rules again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if hit and now - hit[0] < RULES_TTL:", S + "ManyShops.test_a_new_key_reads_the_rules_again"),
    ("the rules are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if False:", S + "OneShop.test_the_rules_and_the_tree_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the tree is read with the rules", "service/app.py", "payrules.tree_of(groups.result())", "payrules.tree_of([])",
     S + "OneShop.test_a_group_takes_the_rule_above_it_from_the_shops_tree"),
    ("a refund reads nothing", "service/app.py", 'if ctx["stage"] != "sale" or not ctx["offered_tenders"]:',
     'if not ctx["offered_tenders"]:', S + "OneShop.test_a_refund_reads_nothing"),
    ("the tree down is a 503", "service/app.py", "            groups = pool.submit(self.api.tree, shop[\"url\"], shop[\"key\"])",
     "            groups = pool.submit(lambda: [])", S + "OneShop.test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules"),
    ("a shop without its key is a 503", "service/app.py", "        if not shop:\n            raise ShopUnreadable",
     "        if False:\n            raise ShopUnreadable", S + "ManyShops.test_a_shop_without_its_integration_key_is_a_503"),
    ("a refusal by the shop is unreadable", "service/app.py",
     'raise kind(f"the shop answered {e.code}") from None',
     "return {}", S + "ShopApi.test_a_refusal_an_error_or_a_404_is_unreadable"),
    ("a refused key is named apart", "service/app.py", "kind = KeyRefused if e.code in (401, 403) else",
     "kind = ShopUnreadable if e.code in (401, 403) else", S + "ShopApi.test_a_refused_key_is_named_apart_from_an_outage"),
    ("empty words fall back", "payrules.py", "    if own.strip(MARKS):\n", "    if True:\n",
     R + "test_words_that_come_out_empty_fall_back_to_the_apps_own"),
    ("the marks are kept", "payrules.py", "if ch.isprintable() or ch in MARKS", "if ch.isprintable()",
     R + "test_the_marks_arabic_and_persian_text_carry_are_kept"),
    ("the refusal's budget keeps the list whole", "payrules.py", "use one with {plain(takes, 58)}", "use one with {plain(takes, 40)}",
     R + "test_the_refusal_keeps_a_long_group_and_method_list_whole"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("only switched-on rules are read", "service/app.py", 'payrules.RULE_FIELDS, [["enabled", "=", 1]])',
     "payrules.RULE_FIELDS, [])", S + "ShopApi.test_reads_every_switched_on_rule_with_its_methods_and_the_token"),
    ("every switched-on rule is read, not one page", "service/app.py", '"limit_page_length": 0})', '"limit_page_length": 20})',
     S + "ShopApi.test_reads_every_switched_on_rule_with_its_methods_and_the_token"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'allow', 'exclude_tenders': ['Cash'], 'reason': 'x'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP PMR Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_rules"),
    ("the check lets the sale go on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_check_switched_off_that_lets_the_sale_go_on_when_down"),
    # 1.1.0: From a sale of (NETT-CRD001)
    ("a method's amount is read from its row", "payrules.py", '            amount = _amount(r.get("min_sale"))',
     "            amount = Decimal(0)", "test_rules.FromASale.test_loyalty_points_left_out_below_the_amount_for_every_customer"),
    ("equal is enough", "payrules.py", "total < need[t]]", "total <= need[t]]",
     "test_rules.FromASale.test_from_the_amount_the_method_is_offered_and_equal_is_enough"),
    ("a minimum is rounded up", "payrules.py", ".to_integral_value(ROUND_CEILING)", ".to_integral_value()",
     "test_rules.FromASale.test_the_amount_is_rounded_up_to_the_sales_minor_unit"),
    ("the largest amount on two rows", "payrules.py", 'elif amount > rule["from"].get(method, 0):', "elif amount:",
     "test_rules.FromASale.test_a_method_on_two_rows_takes_the_strictest"),
    ("a blank row keeps a method out under but these", "payrules.py", '            out[group]["from"].pop(method, None)',
     "            pass", "test_rules.FromASale.test_a_method_on_two_rows_takes_the_strictest"),
    ("a blank row keeps the amount under only these", "payrules.py", '        if out[group]["kind"] == BUT:', "        if True:",
     "test_rules.FromASale.test_a_method_on_two_rows_takes_the_strictest"),
    ("the feed registration stays as listed", "manifest.json", '"description": "the payment method rules service reads', '"description": "the service reads',
     M + "test_the_feed_registration_is_as_listed"),
    ("the amount leads a mixed reason", "payrules.py", "    if short and not own.strip(MARKS):", "    if out == short and not own.strip(MARKS):",
     "test_rules.FromASale.test_every_method_but_these_still_leaves_out_a_row_with_no_amount"),
    ("a 1.0.x retailer's answers are 1.0's", "payrules.py", '    if short and not own.strip(MARKS):', "    if not own.strip(MARKS):",
     "test_rules.FromASale.test_a_retailer_on_the_listed_version_gets_the_same_answers"),
    ("a row with an amount is offered from it under but these", "payrules.py",
     '(t in rule["methods"] and t not in need) or t in short]', '(t in rule["methods"]) or t in short]',
     "test_rules.FromASale.test_from_the_amount_the_method_is_offered_and_equal_is_enough"),
    ("only these leaves out a method below its amount", "payrules.py",
     'if t not in rule["methods"] or t in short]', 'if t not in rule["methods"]]',
     "test_rules.FromASale.test_only_these_offers_a_method_with_an_amount_only_from_it"),
    ("but these leaves out a method below its amount", "payrules.py",
     'and t not in need) or t in short]', "and t not in need)]",
     "test_rules.FromASale.test_loyalty_points_left_out_below_the_amount_for_every_customer"),
    ("the retailer's own words win over the amount", "payrules.py", "    if short and not own.strip(MARKS):",
     "    if short:", "test_rules.FromASale.test_the_retailers_own_words_win"),
    ("nothing left to pay with names the amount", "payrules.py", "if len(out) == len(offered) and short:", "if False:",
     "test_rules.FromASale.test_nothing_left_to_pay_with_is_refused_naming_the_amount"),
    ("an amount that is not a finite number above 0 is no amount", "payrules.py",
     "return d if d.is_finite() and d > 0 else Decimal(0)", "return d",
     "test_rules.FromASale.test_a_blank_zero_negative_or_odd_amount_keeps_the_rules_meaning"),
    ("the check needs its grand total", "payrules.py",
     'if not _whole(exp) or not 0 <= exp <= 4 or not isinstance(totals, dict) or not _whole(totals.get("grand_minor")):',
     "if False:", "test_rules.FromASale.test_the_check_needs_its_exponent_and_grand_total"),
    ("a 417 is read again with the listed fields", "service/app.py",
     "        except FieldMissing:\n", "        except ZeroDivisionError:\n",
     S + "ShopApi.test_a_retailer_on_the_listed_version_is_read_again_without_the_amount"),
    ("a 417 is named a missing field", "service/app.py", "else FieldMissing if e.code == 417 else", "else",
     S + "ShopApi.test_a_retailer_on_the_listed_version_is_read_again_without_the_amount"),
    ("the second read leaves the amount out", "service/app.py", "payrules.RULE_FIELDS_LISTED, [[", "payrules.RULE_FIELDS, [[",
     S + "ShopApi.test_a_retailer_on_the_listed_version_is_read_again_without_the_amount"),
    ("the amount field is on the method rows", "manifest.json", '"fieldname": "min_sale"', '"fieldname": "min_amount"',
     M + "test_one_rule_per_group_named_by_it_with_the_fields_the_service_reads"),
    ("the methods table is required", "manifest.json", '"options": "PP PMR Rule Method",\n     "reqd": 1,', '"options": "PP PMR Rule Method",\n     "reqd": 0,',
     M + "test_one_rule_per_group_named_by_it_with_the_fields_the_service_reads"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s46-canary-")
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
