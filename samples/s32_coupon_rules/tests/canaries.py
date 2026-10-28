#!/usr/bin/env python3
"""S32's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``), copied: a defect there is a defect here.

    python3 samples/s32_coupon_rules/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("the group rule refuses outside its group", "coupons.py", 'if group and (ctx.get("customer_group") or "") != group:',
     "if False:", R + "test_a_group_coupon_is_refused_outside_its_group"),
    ("a group matches exactly", "coupons.py", '(ctx.get("customer_group") or "") != group:',
     'not (ctx.get("customer_group") or "").startswith(group):', R + "test_a_group_matches_exactly_so_a_group_under_it_is_refused"),
    ("a returning customer is refused a first-purchase coupon", "coupons.py", "if prior_sales(customer) > 0:", "if False:",
     R + "test_a_first_purchase_coupon_is_refused_for_a_customer_who_has_bought"),
    ("one earlier sale is enough", "coupons.py", "if prior_sales(customer) > 0:", "if prior_sales(customer) > 1:",
     S + "OneShop.test_a_back_office_sale_counts_as_bought_before"),
    ("no customer is refused a first-purchase coupon", "coupons.py", "        if not customer:\n", "        if False:\n",
     R + "test_a_first_purchase_coupon_with_no_customer_is_refused_without_a_count"),
    ("a switched-off rule refuses nothing", "coupons.py", 'if not r.get("enabled") or not isinstance(coupon, str)',
     "if not isinstance(coupon, str)", R + "test_a_coupon_with_no_rule_or_a_switched_off_rule_is_never_refused"),
    ("sentences are plain", "coupons.py", '.replace("<", "").replace(">", "")', "",
     R + "test_every_sentence_is_plain_and_at_most_140"),
    ("coupon_codes must be a list of text", "coupons.py",
     "if not isinstance(codes, list) or not all(isinstance(c, str) for c in codes):", "if False:",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the cap refuses a sale below what its coupons need", "coupons.py", "    if need <= total:\n", "    if True:\n",
     "test_rules.Cap.test_one_coupon_needs_its_sale"),
    ("exactly the sale needed is allowed", "coupons.py", "    if need <= total:\n", "    if need < total:\n",
     "test_rules.Cap.test_exactly_the_sale_needed_is_allowed"),
    ("each capped coupon takes its own share", "coupons.py", "    need = sum(", "    need = max(",
     "test_rules.Cap.test_two_coupons_need_twice_the_sale"),
    ("a return is never capped", "coupons.py", 'if ctx["stage"] != "sale" or not capped:', "if not capped:",
     "test_rules.Cap.test_a_return_is_never_capped"),
    ("the cap comes before the count", "coupons.py", "    capped = over_cap(ctx, rules, mine)\n    if capped:\n        return capped\n",
     "", "test_rules.Cap.test_the_cap_reads_nothing_and_comes_before_the_count"),
    ("the amount is in the sale's minor units", "coupons.py", "(rules[c][\"spend\"] * 10 ** exp)", "(rules[c][\"spend\"] * 100)",
     "test_rules.Cap.test_the_amount_rounds_half_up_in_the_sales_currency"),
    ("a non-positive or odd amount caps nothing", "coupons.py", 'return d if d.is_finite() and d > 0 else Decimal(0)', "return d",
     "test_rules.RulesOf.test_a_sale_needed_is_a_positive_amount_or_nothing"),
    ("long names keep the instruction", "coupons.py", "    if len(lead + tail) > TEXT_MAX:", "    if False:",
     "test_rules.Cap.test_long_names_keep_the_amounts_and_the_instruction"),
    ("totals are checked before any decision", "coupons.py",
     'or not isinstance(totals, dict) or not _whole(totals.get("grand_minor")):', ":",
     "test_rules.Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the rules are read whole, so a retailer on 1.0.1 still reads", "service/app.py", '{"fields": json.dumps(["*"]),',
     '{"fields": json.dumps(list(coupons.RULE_FIELDS)),', S + "ShopApi.test_reads_every_switched_on_rule_with_the_token"),
    ("the sale needed is never required", "manifest.json", '"label": "Sale needed for each use", "in_list_view": 1,',
     '"label": "Sale needed for each use", "in_list_view": 1, "reqd": 1,', M + "test_the_sale_needed_is_an_optional_amount"),
    ("the signature is checked", "service/app.py", "if not secrets or all(coupons.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_check_takes_only_its_own_secret"),
    ("an old timestamp is refused", "coupons.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("the rules are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_rules_are_kept_per_shop"),
    ("a new key reads the rules again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if hit and now - hit[0] < RULES_TTL:", S + "ManyShops.test_a_new_key_reads_the_rules_again"),
    ("the rules are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if False:", S + "OneShop.test_the_rules_are_read_with_the_apps_key_and_kept_a_minute"),
    ("a sale with no coupon reads nothing", "service/app.py", 'if not ctx["coupon_codes"]:', "if False:",
     S + "OneShop.test_a_sale_with_no_coupon_reads_nothing"),
    ("a back-office sale counts", "service/app.py",
     '         ("Sales Invoice", [["docstatus", "=", 1], ["is_return", "=", 0], ["is_consolidated", "=", 0]]))', "         )",
     S + "OneShop.test_a_back_office_sale_counts_as_bought_before"),
    ("a return is not a purchase", "service/app.py", '(("POS Invoice", [["docstatus", "=", 1], ["is_return", "=", 0]]),',
     '(("POS Invoice", [["docstatus", "=", 1]]),', S + "OneShop.test_a_new_customer_is_counted_at_the_till_and_in_the_back_office"),
    ("a consolidated invoice is not counted twice", "service/app.py", ', ["is_consolidated", "=", 0]]))', "]))",
     S + "OneShop.test_a_new_customer_is_counted_at_the_till_and_in_the_back_office"),
    ("a refused key refuses the coupon in words", "service/app.py",
     'return 200, {"verdict": "refuse", "reason": KEY_REFUSED}', 'return 503, {"error": "x"}',
     S + "OneShop.test_a_refused_key_refuses_a_ruled_coupon_in_words"),
    ("a refused count refuses the coupon, never allows it", "service/app.py",
     'return 200, {"verdict": "refuse", "reason": KEY_REFUSED}', 'return 200, {"verdict": "allow"}',
     S + "OneShop.test_the_count_alone_refused_refuses_the_coupon_in_words"),
    ("both ledgers are added", "service/app.py", "return sum(pool.map(", "return min(pool.map(",
     S + "OneShop.test_both_ledgers_are_counted_at_once_and_added"),
    ("401 and 403 are a refused key", "service/app.py", "raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)",
     "raise ShopUnreadable", S + "ShopApi.test_a_refusal_is_key_refused_and_an_error_or_404_is_unreadable"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("a count is a whole number", "service/app.py", "if not isinstance(n, int) or isinstance(n, bool) or n < 0:",
     "if n is None:", S + "ShopApi.test_a_count_that_is_not_a_whole_number_is_unreadable"),
    ("the count uses the shop's iVendNext name", "service/app.py", '"/api/method/ivendnext_mpos.api.v1.get_count"',
     '"/api/method/other.get_count"', S + "ShopApi.test_counts_through_the_shops_ivendnext_name"),
    ("every switched-on rule is read, not one page", "service/app.py", '"limit_page_length": 0})', '"limit_page_length": 20})',
     S + "ShopApi.test_reads_every_switched_on_rule_with_the_token"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'allow'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP CPN Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_rules"),
    ("the check lets the sale go on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_check_switched_off_that_lets_the_sale_go_on_when_down"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s32-canary-")
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
