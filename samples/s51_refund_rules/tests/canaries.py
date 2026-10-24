#!/usr/bin/env python3
"""S51's canaries: each test that guards a rule, a secret or a read of the retailer must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and a Python
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``, by S32, S46 and S50), copied: a defect there is a defect here.

    python3 samples/s51_refund_rules/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M, D = "test_rules.", "test_service.", "test_manifest.ManifestTest.", "refunds.py"

CANARIES = [
    ("other methods are taken off", D, "    off = [t for t in dict.fromkeys(offered) if t not in keep]",
     "    off = []", R + "SameMethods.test_a_card_sale_is_refunded_by_card_or_store_credit_only"),
    ("the methods that paid stay", D, '        keep = list(ro["paid_by"]) + settings["always"] + credit',
     '        keep = settings["always"] + credit', R + "SameMethods.test_every_method_that_paid_the_sale_stays"),
    ("the always-allowed methods stay", D, '        keep = list(ro["paid_by"]) + settings["always"] + credit',
     '        keep = list(ro["paid_by"]) + credit', R + "SameMethods.test_the_always_allowed_methods_stay"),
    ("store credit is never taken off", D, '        keep = list(ro["paid_by"]) + settings["always"] + credit',
     '        keep = list(ro["paid_by"]) + settings["always"]',
     R + "SameMethods.test_the_store_credit_method_is_never_taken_off_so_an_exchange_goes_on"),
    ("nothing left refuses", D, "    if len(off) == len(dict.fromkeys(offered)):", "    if False:",
     R + "SameMethods.test_none_of_the_sales_methods_offered_refuses_the_refund"),
    ("the methods rule can be off", D, '    elif settings["same_methods"]:', "    elif True:",
     R + "SameMethods.test_the_rule_switched_off_lets_every_method_through"),
    ("no more than twenty are taken off", D, "    if len(off) > EXCLUDE_MAX:", "    if False:",
     R + "SameMethods.test_more_methods_to_take_off_than_the_check_may_is_a_refusal"),
    ("a return without its sale keeps only the named", D, '        keep = settings["without_sale"] + credit',
     '        keep = list(offered)', R + "WithoutItsSale.test_a_return_without_its_sale_goes_back_by_the_methods_named"),
    ("none named leaves it as today", D, '        if not settings["without_sale"]:\n            return {"verdict": "allow"}',
     '        if False:\n            return {"verdict": "allow"}', R + "WithoutItsSale.test_none_named_leaves_it_as_today"),
    ("a sale is never judged", D, '    if ctx["stage"] != "return" or ctx["totals"]["grand_minor"] >= 0 or not settings:',
     '    if not settings:', R + "NotJudged.test_a_sale_is_never_judged"),
    ("money going nowhere is not judged", D,
     '    if ctx["stage"] != "return" or ctx["totals"]["grand_minor"] >= 0 or not settings:',
     '    if ctx["stage"] != "return" or not settings:', R + "NotJudged.test_a_return_whose_money_goes_nowhere_is_not_judged"),
    ("a tick reads as on only when it is", D, '"same_methods": doc.get("same_methods") in (1, "1", True),',
     '"same_methods": bool(doc.get("same_methods")),', R + "Settings.test_a_tick_reads_as_on_only_when_it_is"),
    ("each method is kept once", D, "        if isinstance(mop, str) and mop and mop not in out:",
     "        if isinstance(mop, str) and mop:", R + "Settings.test_the_record_and_its_two_tables"),
    ("a context of the wrong shape is refused", D,
     "    if not _texts(ctx.get(\"offered_tenders\")):", "    if False:",
     R + "Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("sentences are plain", D, '.replace("<", "").replace(">", "")', "", R + "Words.test_every_sentence_is_plain_and_at_most_140"),
    ("the marks are kept", D, "if ch.isprintable() or ch in MARKS", "if ch.isprintable()",
     R + "Words.test_the_marks_arabic_and_persian_text_carry_are_kept"),
    ("the signature is checked", "service/app.py", "if not secrets or all(refunds.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_the_check_takes_only_its_own_secret"),
    ("an old timestamp is refused", D, "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("a long timestamp is refused, never parsed", D, "ts.isdigit() and len(ts) <= 12)", "ts.isdigit())",
     R + "Verify.test_the_signature_and_the_time_are_checked"),
    ("the settings are kept per retailer", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_settings_are_kept_per_retailer"),
    ("a new key reads the settings again", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if hit and now - hit[0] < RULES_TTL:", S + "ManyShops.test_a_new_key_reads_the_settings_again"),
    ("the settings are kept a minute", "service/app.py", 'if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:',
     "if False:", S + "OneShop.test_the_settings_are_read_with_the_apps_key_and_kept_a_minute"),
    ("a sale reads nothing", "service/app.py", '        if ctx["stage"] != "return" or ctx["totals"]["grand_minor"] >= 0:\n            return 200',
     '        if False:\n            return 200', S + "OneShop.test_a_sale_and_a_refund_of_nothing_read_nothing"),
    ("a retailer without its key is a 503", "service/app.py", "        if not shop:\n            raise ShopUnreadable",
     "        if False:\n            raise ShopUnreadable", S + "ManyShops.test_a_retailer_without_its_integration_key_is_a_503"),
    ("no settings record is every rule off", "service/app.py", "        except Missing:\n            return None",
     "        except KeyError:\n            return None", S + "ShopApi.test_no_settings_record_is_none"),
    ("a refused key is named apart", "service/app.py", "raise (KeyRefused if e.code in (401, 403) else Missing",
     "raise (ShopUnreadable if e.code in (401, 403) else Missing", S + "ShopApi.test_a_refused_key_is_named_apart_from_an_outage"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'refuse', 'reason': 'x'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '"role": "PP RFR Integration"', '"role": "PP Integration"',
     M + "test_the_integration_role_only_reads_the_settings"),
    ("the check lets the refund go on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_check_switched_off_that_lets_the_refund_go_on_when_down"),
    ("store credit is required with the methods rule", "manifest.json", '"mandatory_depends_on": "same_methods",', "",
     M + "test_the_settings_record_is_named_default_with_the_fields_the_service_reads"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s51-canary-")
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
