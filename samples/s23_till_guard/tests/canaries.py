#!/usr/bin/env python3
"""S23's canaries: each test that guards a rule, a secret or the shop's settings must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S22's.

    python3 samples/s23_till_guard/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CANARIES = [
    ("the signature is checked", "service/app.py", "if not secrets or all(guard.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", "test_service.OneShop.test_each_route_takes_only_its_own_secret"),
    ("each route takes its own secret (one shop)", "service/app.py", 'return "-", [self.secrets[route_key]], self.shop',
     'return "-", list(self.secrets.values()), self.shop', "test_service.OneShop.test_each_route_takes_only_its_own_secret"),
    ("each route takes its own secret (many shops)", "service/app.py", 'f"{self.app}:sub:{route_key}"',
     'f"{self.app}:sub:guard"', "test_service.ManyShops.test_the_scan_route_takes_the_scan_secret_only"),
    ("an old timestamp is refused", "guard.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     "test_service.OneShop.test_an_old_timestamp_is_refused"),
    ("the placeholder price is refused", "guard.py", "if floor and 0 < line", "if False and 0 < line",
     "test_guard.CheckRules.test_a_line_at_the_placeholder_price_is_refused_in_our_words"),
    ("a free line is never refused", "guard.py", "0 < line[\"rate_minor\"] <= floor", "line[\"rate_minor\"] <= floor",
     "test_guard.CheckRules.test_a_free_line_priced_zero_is_never_refused"),
    ("more than the most is refused", "guard.py", "if most and line", "if False and line",
     "test_guard.CheckRules.test_more_than_the_most_on_one_line_is_refused"),
    ("exactly the most is allowed", "guard.py", 'line["qty_milli"] > most', 'line["qty_milli"] >= most',
     "test_guard.CheckRules.test_exactly_the_most_is_allowed"),
    ("the approval amount itself needs a manager", "guard.py", 'ctx["totals"]["grand_minor"] >= limit',
     'ctx["totals"]["grand_minor"] > limit', "test_guard.CheckRules.test_a_large_sale_calls_a_manager"),
    ("what a return takes back is never judged", "guard.py", 'for line in ctx["lines"] if line["qty_milli"] > 0]',
     'for line in ctx["lines"]]', "test_guard.CheckRules.test_what_a_return_takes_back_is_never_judged"),
    ("an exchange's returned line is not judged", "guard.py", 'for line in ctx["lines"] if line["qty_milli"] > 0]',
     'for line in ctx["lines"]]', "test_guard.CheckRules.test_an_exchanges_returned_line_is_not_judged"),
    ("an exchange's sold line is judged", "guard.py", "    for line in sold_lines(ctx):\n",
     '    for line in (sold_lines(ctx) if ctx["stage"] == "sale" else []):\n',
     "test_guard.CheckRules.test_an_exchanges_sold_line_at_the_placeholder_price_is_refused"),
    ("an exchange that takes a large payment calls a manager", "guard.py", '    if rules["approval_from"]:',
     '    if rules["approval_from"] and ctx["stage"] == "sale":',
     "test_guard.CheckRules.test_an_exchange_that_takes_a_large_payment_calls_a_manager"),
    ("an exchange reads the shop", "service/app.py", 'and ctx["stage"] != "sale" and not guard.sold_lines(ctx):',
     'and ctx["stage"] != "sale":',
     "test_service.OneShop.test_an_exchange_reads_the_shop_and_judges_what_it_sells"),
    ("sentences are plain", "guard.py", '.replace("<", "").replace(">", "")', "",
     "test_guard.CheckRules.test_every_sentence_is_plain_and_at_most_140"),
    ("the settings are kept a minute", "service/app.py", "if hit and now - hit[0] < SETTINGS_TTL:", "if False:",
     "test_service.OneShop.test_the_settings_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the last rules stand in for ten minutes only", "service/app.py", "if hit and now - hit[0] < SETTINGS_STALE:", "if hit:",
     "test_service.OneShop.test_the_shop_down_uses_the_last_rules_for_ten_minutes_then_503"),
    ("the cache is per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     "test_service.ManyShops.test_each_shop_is_answered_from_its_own_rules_with_its_own_key"),
    ("a return reads nothing from the shop", "service/app.py", 'if path == "/tgr/check" and ctx["stage"] != "sale" and not',
     "if False and not", "test_service.OneShop.test_a_return_is_allowed_without_reading_the_shop"),
    ("a 404 is 'no record' only when it names the record", "service/app.py",
     'if e.code == 404 and f"{prefix} Settings Default".encode() in body:', "if e.code == 404:",
     "test_service.ShopApi.test_a_404_that_does_not_name_the_record_is_unreadable_never_rules_off"),
    ("a blank large-sale answer asks the cashier", "guard.py", 'answer = (doc.get("approval_answer") or "ask")',
     'answer = (doc.get("approval_answer") or "approve")',
     "test_guard.CheckRules.test_a_blank_or_unknown_approval_answer_asks_the_cashier"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'allow'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     "test_service.AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP TGR Integration"', '"role": "PP Integration"',
     "test_manifest.ManifestTest.test_the_integration_role_only_reads_the_settings"),
    ("a sale with no sold line reads the shop", "service/app.py", 'and ctx["stage"] != "sale" and not guard.sold_lines(ctx):',
     'and not guard.sold_lines(ctx):', "test_service.OneShop.test_a_sale_with_no_sold_line_still_reads_the_shop"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)",
     "urllib.request.build_opener()", "test_service.ShopApi.test_a_redirect_is_not_followed"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s23-canary-")
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
