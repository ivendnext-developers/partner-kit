#!/usr/bin/env python3
"""S35's canaries: each test that guards a shop's secret, its key, the order's other fields, a concurrent edit or the
service's words must go RED when that check is removed. For each mutation this copies the sample (and the kit folders it
uses) to a temporary folder, runs the one test named on the unmutated copy (it must pass, else BROKEN), applies ONE change
(the anchor must match exactly once, and the mutant must compile), runs the test again, and reports RED (the test caught
it) or GREEN (a dead test). The runner is S16's.

    python3 samples/s35_call_centre_orders/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, S, R = "test_service.ServiceTest.", "test_many_shops.", "service/app.py", "route.py"

CANARIES = [
    ("the signature is checked", S, "        if not secrets or all(route.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", M + "ManyShops.test_another_shops_secret_an_unknown_site_and_no_site_are_refused"),
    ("each shop's own secret", S, "record = self.store.get(site) if site else None",
     "record = self.store.get(self.store.sites()[0]) if site else None",
     M + "ManyShops.test_another_shops_secret_an_unknown_site_and_no_site_are_refused"),
    ("each shop's own user key", S, 'if k.startswith("user:") and k != "user:Administrator")', 'if ":" in k)',
     M + "ManyShops.test_each_shop_is_written_with_its_own_key_under_the_librarys_field"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")",
     M + "ManyShops.test_administrators_key_is_never_used"),
    ("a press before Connect again is answered in words", S, "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n",
     "", M + "ManyShops.test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("a refused user is named in words", S, "            if e.code in (401, 403):", "            if False:",
     T + "test_s9_the_apps_user_refused_by_the_shop_is_said_in_words"),
    ("the write names the order as it was read", R, '    return {"set_warehouse": store, "items": lines, "modified": order["modified"]}',
     '    return {"set_warehouse": store, "items": lines}', T + "test_s1_an_order_goes_to_its_districts_own_store_on_the_header_and_every_line"),
    ("a stale write is never retried from the stale read", S, "                if e.kind == STALE and attempt == 1:",
     "                if False:", T + "test_s7_an_edit_saved_between_the_read_and_the_write_is_never_written_over"),
    ("only a draft is written", S, "            if order.get(\"docstatus\") != 0:", "            if False:",
     T + "test_s6_a_submitted_order_is_never_written"),
    ("a supplier's line keeps its warehouse", R, '    return not line.get("delivered_by_supplier")', "    return True",
     T + "test_s1_an_order_goes_to_its_districts_own_store_on_the_header_and_every_line"),
    ("the walk goes up the tree", R, '        name = row.get("parent_territory")', "        name = None",
     T + "test_s2_a_district_without_a_store_takes_the_store_above_it"),
    ("a routed order is not written again", S, "            if route.routed(order, store):", "            if False:",
     T + "test_s3_a_second_press_changes_nothing_and_says_where_the_order_is"),
    ("a store that cannot ship is never written", S, "            if not route.can_ship(wh, order):", "            if False:",
     T + "test_s8b_a_group_a_disabled_or_another_companys_store_is_never_written"),
    ("a group is not a store", R, '    return (not warehouse.get("is_group") and not warehouse.get("disabled")',
     '    return (not warehouse.get("disabled")', T + "test_s8b_a_group_a_disabled_or_another_companys_store_is_never_written"),
    ("another company's store is not this order's", R, '            and warehouse.get("company") == order.get("company"))',
     "            and True)", T + "test_s8b_a_group_a_disabled_or_another_companys_store_is_never_written"),
    ("a refused store is named in words", S, "                if e.code == 417:", "                if False:",
     T + "test_s8_a_store_the_shop_refuses_is_named_in_the_services_own_words"),
    ("one order a press", R, "    if len(ctx[\"records\"]) != 1:", "    if not ctx[\"records\"]:",
     T + "test_a_press_must_name_exactly_one_sales_order"),
    ("a long name is cut to the answer's limit", R, "    return text if len(text) <= most else text[: most - 1] + \"…\"",
     "    return text", T + "test_a_long_store_name_is_cut_to_the_answers_limit"),
    ("the prefix names the field", R, '    FIELD = prefix.lower().replace(" ", "_") + "_store"', "    FIELD = FIELD",
     M + "Prefix.test_the_field_follows_the_prefix_and_the_manifest_names_it"),
    ("a redirect is not followed", S, "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     M + "ShopApi.test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else"),
    ("a cut answer is an unknown outcome", S, "(OSError, ValueError, http.client.HTTPException) as e:     # OSError",
     "(OSError, ValueError) as e:     # OSError", M + "ShopApi.test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash"),
    ("the shop's error type is read", S, "            kind = _kind(e)", "            kind = \"\"",
     M + "ShopApi.test_a_stale_write_is_named_by_the_shops_error_type_and_its_message_is_dropped"),
    ("the function checks the signature too", S, "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'ok': 1}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     M + "AsAFunction.test_health_a_signed_press_either_body_form_and_a_refusal"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s35-canary-")
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
