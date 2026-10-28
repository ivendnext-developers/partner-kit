#!/usr/bin/env python3
"""S16's canaries: each test that guards a shop's secret, its key, its words or the claim on a press must go RED when that
check is removed. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the
one test named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once,
and the mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The
runner is S23's.

    python3 samples/s16_pick_route/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, S, TPL = "test_many_shops.ManyShops.", "service/app.py", "../../tools/app_template/service/shops.py"

CANARIES = [
    ("the signature is checked", S, "        if not secrets or all(route.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:",
     T + "test_another_shops_secret_an_unknown_site_and_no_site_are_refused"),
    ("each shop's own secret", S, "record = self.store.get(site) if site else None",
     "record = self.store.get(self.store.sites()[0]) if site else None",
     T + "test_another_shops_secret_an_unknown_site_and_no_site_are_refused"),
    ("the previous secret while a shop moves", S, 'shops.secrets_for(record, f"{self.app}:sub:{SUB}")',
     '[((record or {}).get("secrets") or {}).get(f"{self.app}:sub:{SUB}", "").encode()]',
     T + "test_a_shop_whose_secret_changed_is_accepted_with_the_previous_one_while_it_moves"),
    ("each shop's own user key", S, 'if k.startswith("user:") and k != "user:Administrator")', 'if ":" in k)',
     T + "test_each_shop_is_written_with_its_own_key_under_the_librarys_names"),
    ("a press before the shop's key arrives is answered in words", S, "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n",
     "", T + "test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403):", "            if False:",
     T + "test_a_shop_that_refuses_the_apps_user_is_told_so_in_words"),
    ("two copies never handle one press", S, "        if not self.store.claim(name, self.clock(), CLAIM_STALE):",
     "        if False:", T + "test_two_copies_receiving_one_press_make_one_task"),
    ("the claim is let go after the press", S, "                self.store.delete(name)", "                pass",
     T + "test_two_copies_receiving_one_press_make_one_task"),
    ("the claim is per shop", S, 'f"press{shops.CLAIM_MARK}{site}{shops.CLAIM_MARK}', 'f"press{shops.CLAIM_MARK}{shops.CLAIM_MARK}',
     T + "test_the_same_key_from_another_shop_is_another_press"),
    ("a stopped copy's claim is taken over once stale", TPL, '.get("at", 0) > now - stale_s:', '.get("at", 0) > 0:',
     T + "test_a_claim_left_by_a_stopped_copy_is_taken_over_once_stale"),
    ("the prefix names the pick task", "route.py", '    TASK = f"{prefix} Pick Task"', "    TASK = TASK",
     "test_many_shops.Prefix.test_every_record_type_name_follows_the_prefix"),
    ("a redirect is not followed", S, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     "test_many_shops.ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("the function checks the signature too", S, "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'ok': 1}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     "test_many_shops.AsAFunction.test_health_a_signed_press_either_body_form_and_a_refusal"),
    ("the integration role carries the prefix", "manifest.json", '{"role": "PP PCK Integration", "read": 1, "write": 0, "create": 1',
     '{"role": "PP Integration", "read": 1, "write": 0, "create": 1', "test_manifest.ManifestTest.test_the_feeds_user_holds_the_apps_own_role"),
    ("a write with no answer keeps the claim", S, '                    held["keep"] = writing and e.code is None', '                    held["keep"] = False',
     T + "test_a_task_saved_after_the_service_stopped_waiting_is_never_made_twice"),
    ("a read with no answer frees the claim", S, '                    held["keep"] = writing and e.code is None',
     '                    held["keep"] = e.code is None', T + "test_a_read_with_no_answer_frees_the_press_at_once"),
    ("a retried list press finds each order's own task", S, '                        row = found.get(t["sales_order"])',
     '                        row = next(iter(found.values()), None)',
     T + "test_a_list_press_retried_after_a_stop_finds_what_was_made_and_makes_the_rest"),
    ("a press carries at most ORDERS_MAX orders", S, "        if len(tasks) > ORDERS_MAX:", "        if False:",
     T + "test_more_orders_than_one_press_may_carry_are_refused_in_words"),
    ("one sentence for every refusal", S, '            return 401, {"error": "the signature does not match"}',
     '            return 401, {"error": next((w for w in (route.verify(ts, sig, raw, x) for x in secrets) if w), "the signature does not match")}',
     T + "test_an_old_press_is_refused_in_the_same_words_as_an_unknown_site"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     T + "test_administrators_key_is_never_used"),
    ("a cut answer is an unknown outcome", S, "(OSError, ValueError, http.client.HTTPException) as e:", "(OSError, ValueError) as e:",
     "test_many_shops.ShopApi.test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s16-canary-")
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
