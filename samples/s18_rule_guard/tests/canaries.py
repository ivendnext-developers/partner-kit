#!/usr/bin/env python3
"""S18's canaries: each check of a shop's call must go RED when it is removed. For each mutation this copies the sample
(and the app template it imports) to a temporary folder, runs the one test named on that unmutated copy (it must pass,
else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs the test
again, and reports RED (the test caught it) or GREEN (a dead test). The shape of samples/s22_customer_loyalty/tests/canaries.py.

    python3 samples/s18_rule_guard/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("the shop the call names, its own route secret", "service/app.py",
     'record = self.store.get(site) if site else None',
     'record = self.store.get((self.store.sites() or [site])[0]) if site else None',
     "test_many_shops.ManyShops.test_canary_the_check_reads_the_route_secret_of_the_shop_it_names"),
    ("a site that never connected", "service/app.py", "self.store.get(site)",
     "(self.store.get(site) or self.store.get(self.store.sites()[0]))",
     "test_many_shops.ManyShops.test_canary_a_site_that_never_connected_is_refused"),
    ("a signature that does not match", "service/app.py", '    if "" not in whys:', "    if False:",
     "test_service.ServiceTest.test_a_forged_check_is_refused"),
    ("the body as signed", "../../tools/app_template/service/function.py", 'else body.encode("utf-8")',
     'else body.encode("ascii", "replace")', "test_many_shops.ManyShops.test_a_basket_in_another_script_and_a_base64_body"),
    ("each shop judged by its own records", "service/app.py",
     'rules = rule.rules_of(self.api.rules(shop["url"], shop["key"], self.prefix))', "rules = self.rules",
     "test_shop_rules.EachShopsOwnRule.test_canary_each_shop_is_judged_by_its_own_records"),
    ("a shop's rule kept a minute, then read again", "service/app.py", 'now - hit[0] < RULES_TTL', "True",
     "test_shop_rules.EachShopsOwnRule.test_canary_the_rule_is_kept_a_minute_then_read_again"),
    ("a new user key reads again", "service/app.py", 'hit[1] == shop["key"] and ', "",
     "test_shop_rules.EachShopsOwnRule.test_a_new_user_key_reads_again_at_once"),
    ("no user key yet: refused in words", "service/app.py", "        if shop is None:\n            return None",
     "        if shop is None:\n            return self.rules",
     "test_shop_rules.EachShopsOwnRule.test_canary_a_shop_with_no_user_key_yet_is_refused_in_words_that_say_so"),
    ("an unreadable shop is down, not allowed", "service/app.py",
     'flush=True)\n            return 503, {"error": "unavailable"}\n        if rules is None:',
     'flush=True)\n            return 200, {"verdict": "allow"}\n        if rules is None:',
     "test_shop_rules.EachShopsOwnRule.test_canary_a_shop_that_cannot_be_read_is_down_not_allowed"),
    ("an item handed back inside a sale is not judged", "rule.py", "    return [ln", '    if ctx["stage"] == "sale":\n        return ctx["lines"]\n    return [ln',
     "test_service.RuleTest.test_an_item_handed_back_inside_a_sale_is_not_judged"),
    ("a line's quantity must be a whole number", "rule.py", 'raise ValueError("a line\'s quantity is a whole number")', "pass",
     "test_service.RuleTest.test_a_context_it_cannot_read_is_refused"),
    ("a return that sells nothing reads nothing", "service/app.py", "if not rule.sold_lines(ctx):", "if False:",
     "test_shop_rules.EachShopsOwnRule.test_a_return_that_sells_nothing_reads_nothing_and_is_allowed"),
    ("an exchange's sold items judged as a sale", "rule.py", 'ln["qty_milli"] > 0]', 'ln["qty_milli"] > 0 and False]',
     "test_shop_rules.EachShopsOwnRule.test_canary_an_exchange_that_sells_a_members_only_item_is_refused"),
    ("a refused key is told apart", "service/app.py", "        except KeyRefused:\n            return 200, {\"verdict\": \"refuse\", \"reason\": KEY_REFUSED}\n", "",
     "test_shop_rules.EachShopsOwnRule.test_canary_a_key_the_shop_refuses_is_refused_in_words_that_say_so"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError, AttributeError)",
     "except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, AttributeError)",
     "test_shop_rules.TheRealRead.test_canary_a_cut_answer_is_the_shop_unreadable_not_a_crash"),
    # the test call (X-iVendNext-Test: 1, tools/app_template/service/testcall.py): checked as a real call, never the handler
    ("a test call never reaches the handler", "service/app.py", "if testcall.is_test(headers):", "if False:",
     "test_service.TestCall.test_a_signed_test_call_is_answered_ok_without_the_handler"),
    ("a test call is answered only where its route matches", "service/app.py",
     '        if path == ROUTE:\n            return self.check(headers, raw)\n',
     '        if testcall.is_test(headers):\n            return testcall.answer("x")\n        if path == ROUTE:\n            return self.check(headers, raw)\n',
     "test_service.TestCall.test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s18-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__", "screenshots", ".env*"))
        shutil.copytree(os.path.join(kit, "tools", "app_template"), os.path.join(tmp, "r", "tools", "app_template"),
                        ignore=shutil.ignore_patterns("__pycache__"))   # app.py imports the template's handshake
        base = subprocess.run([sys.executable, "-m", "unittest", test], cwd=os.path.join(dest, "tests"),
                              capture_output=True, text=True, timeout=120)
        if base.returncode:              # the test must pass on the unmutated copy, or a RED below proves nothing
            return "BROKEN", "fails before the mutation: " + ((base.stderr.strip().splitlines() or [""])[-1])
        f = os.path.normpath(os.path.join(dest, path))
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
