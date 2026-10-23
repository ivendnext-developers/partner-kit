#!/usr/bin/env python3
"""S42's canaries: each test that guards a rule, a secret or a read of the shop must go RED when that rule is broken.
For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs the one test named on
the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant
must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S23's
(``samples/s23_till_guard/tests/canaries.py``), copied: a defect there is a defect here.

    python3 samples/s42_optical_prescriptions/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R, S, M = "test_rules.", "test_service.", "test_manifest.ManifestTest."

CANARIES = [
    # the rules
    ("a group's mark covers the groups below it", "optical.py", "if g and mark and lft <= g[0] and g[1] <= rgt]",
     "if g and mark and lft == g[0]]", R + "Marks.test_a_groups_mark_covers_the_groups_below_it"),
    ("the nearest group wins (Not needed frees a group below)", "optical.py", "own = max(above)[1] if above else \"\"",
     "own = min(above)[1] if above else \"\"", R + "Marks.test_not_needed_below_a_marked_group_frees_it"),
    ("an item's own mark wins", "optical.py", "    own = own or (items.get(template) or (\"\", \"\"))[0]\n    if not own:",
     "    own = own or (items.get(template) or (\"\", \"\"))[0]\n    if True:", R + "Marks.test_an_items_own_mark_wins_over_its_group"),
    ("a variant takes its template's mark", "optical.py", "    own = own or (items.get(template) or (\"\", \"\"))[0]\n", "",
     R + "Marks.test_a_variant_with_no_mark_of_its_own_takes_its_templates"),
    ("a value that is not a mark is none", "optical.py", "return v if v in KINDS or v == NOT_NEEDED else \"\"",
     "return v if isinstance(v, str) else \"\"", R + "Marks.test_a_value_that_is_not_one_of_the_marks_is_none"),
    ("Not needed is no need", "optical.py", "return own if own in KINDS else \"\"", "return own",
     R + "Marks.test_not_needed_below_a_marked_group_frees_it"),
    ("a prescription is in date only to its last day", "optical.py", "return k == kind and until is not None and today <= until",
     "return k == kind and until is not None", R + "Prescriptions.test_in_date_is_its_kind_valid_until_today_or_later"),
    ("a prescription answers its own kind only", "optical.py", "return k == kind and until is not None and today <= until",
     "return k in KINDS and until is not None and today <= until", R + "Check.test_a_prescription_of_the_other_kind_does_not"),
    ("a record without its fields is unreadable", "optical.py", '{"kind", "valid_until"} <= set(r) for r in records):',
     "True for r in records):", R + "Prescriptions.test_a_record_without_its_kind_and_valid_until_is_unreadable"),
    ("a group without the mark's field is refused", "optical.py", 'and isinstance(r.get("rgt"), int) and field in r for r in records):',
     'and isinstance(r.get("rgt"), int) for r in records):', R + "Context.test_a_group_or_item_without_the_marks_field_is_refused"),
    ("an item without the mark's field is refused", "optical.py", 'isinstance(r, dict) and isinstance(r.get("name"), str) and field in r for r in records):',
     'isinstance(r, dict) and isinstance(r.get("name"), str) for r in records):', S + "OneShop.test_items_without_their_mark_are_a_503_not_unmarked"),
    ("the test date is not judged", "optical.py", "return k == kind and until is not None and today <= until",
     "return k == kind and until is not None and today <= until and False", R + "Check.test_the_test_date_is_not_judged"),
    ("an unreadable date is none", "optical.py", "        return datetime.date.fromisoformat(v[:10])\n    except ValueError:\n        return None",
     "        return datetime.date.fromisoformat(v[:10])\n    except ValueError:\n        return datetime.date.min",
     R + "Prescriptions.test_an_unreadable_date_or_kind_counts_as_none"),
    ("the shop's own day", "optical.py", "(t + datetime.timedelta(hours=hours)).date()", "t.date()",
     R + "Prescriptions.test_today_is_the_shops_own_day"),
    ("hours past 14 read 0", "optical.py", "and -14 <= hours <= 14 else 0.0", "else 0.0",
     R + "Prescriptions.test_settings_hours_are_a_number_within_14"),
    ("a lens line with none is refused", "optical.py", "or any(in_date(rx, kind, today) for rx in rxs):", "or True:",
     R + "Check.test_a_lens_line_with_no_prescription_is_refused_naming_it"),
    ("a prescription in date allows", "optical.py", "or any(in_date(rx, kind, today) for rx in rxs):", "or False:",
     R + "Check.test_a_prescription_of_the_kind_in_date_allows"),
    ("a return's taken-back line is not judged", "optical.py", 'if line["qty_milli"] <= 0 or not kind', "if not kind",
     R + "Check.test_a_return_is_judged_only_for_what_it_sells"),
    ("the day it ran out is named", "optical.py", "        if ended:\n", "        if False:\n",
     R + "Check.test_an_expired_one_names_the_day_it_ran_out"),
    ("the latest ended one is named", "optical.py", "            d = max(ended)\n", "            d = min(ended)\n",
     R + "Check.test_the_latest_ended_one_is_named"),
    ("the refusal's item is cut to fit", "optical.py", 'plain(line["item_code"], 20)', 'plain(line["item_code"], 40)',
     R + "Check.test_every_refusal_is_plain_and_at_most_140"),
    ("sentences are plain", "optical.py", '.replace("<", "").replace(">", "")', "", R + "Check.test_every_refusal_is_plain_and_at_most_140"),
    ("the shape is checked first", "optical.py", 'and _number(x.get("qty_milli")) for x in lines):', "for x in lines):",
     R + "Context.test_a_bad_shape_is_refused_before_any_decision"),
    ("the customer is text", "optical.py", '    if not isinstance(ctx.get("customer"), str):\n', "    if False:\n",
     R + "Context.test_a_bad_shape_is_refused_before_any_decision"),
    # the service
    ("a refund reads nothing", "service/app.py", "        if not optical.sells(ctx):\n", "        if False:\n",
     S + "OneShop.test_a_refund_is_allowed_without_reading_anything"),
    ("no need reads no prescription", "service/app.py", "        if not any(needs):\n", "        if False:\n",
     S + "OneShop.test_nothing_needing_a_prescription_reads_no_prescription"),
    ("a returned line needs nothing", "service/app.py", 'if x["qty_milli"] > 0 else ""', 'if True else ""',
     S + "OneShop.test_a_returned_lens_line_reads_no_prescription"),
    ("the sale's customer is read", "service/app.py", 'self.prefix, ctx["customer"]))', 'self.prefix, "Ana Lopez"))',
     S + "OneShop.test_a_walk_in_or_unknown_customer_is_refused_naming_the_line"),
    ("the shop's day comes from its hours", "service/app.py", 'optical.today_at(settings["hours"], self.now())',
     "optical.today_at(0, self.now())", S + "OneShop.test_the_shops_hours_decide_today"),
    ("the signature is checked", "service/app.py", "if not secrets or all(optical.verify(ts, sig, raw, s) for s in secrets):",
     "if not secrets:", S + "OneShop.test_only_its_own_secret_is_taken"),
    ("an old timestamp is refused", "optical.py", "abs((now or time.time()) - int(ts)) > SKEW_S", "False",
     S + "OneShop.test_an_old_timestamp_is_refused"),
    ("an item the shop does not return is unreadable", "service/app.py", "                if set(missing) - set(read):\n",
     "                if False:\n", S + "OneShop.test_an_item_the_shop_does_not_return_is_a_503"),
    ("the settings and groups are kept a minute", "service/app.py", "if not (hit and hit[1] == key and now - hit[0] < KEPT_TTL):",
     "if True:", S + "OneShop.test_the_settings_groups_and_items_are_read_with_the_apps_key_and_kept_a_minute"),
    ("only the items not kept are read", "service/app.py", "            missing = sorted(set(codes) - set(items))\n",
     "            missing = sorted(set(codes))\n", S + "OneShop.test_the_settings_groups_and_items_are_read_with_the_apps_key_and_kept_a_minute"),
    ("the service reads a variant's template", "service/app.py", "        for _step in range(2):", "        for _step in range(1):",
     S + "OneShop.test_a_variant_is_judged_by_its_templates_mark_read_in_a_second_step"),
    ("the marks are kept per shop", "service/app.py", 'return site or "", secrets, shop', 'return "-", secrets, shop',
     S + "ManyShops.test_the_marks_are_kept_per_shop"),
    ("a new key reads the shop again", "service/app.py", "if not (hit and hit[1] == key and now - hit[0] < KEPT_TTL):",
     "if not (hit and now - hit[0] < KEPT_TTL):", S + "ManyShops.test_a_new_key_reads_the_shop_again"),
    ("a new key reads the items again", "service/app.py", "        mine = (name, key)  ", "        mine = (name, '')  ",
     S + "ManyShops.test_a_new_key_reads_the_shop_again"),
    ("a missing settings record is none, not an error", "service/app.py", "            if missing and e.code == 404:\n",
     "            if False:\n", S + "ShopApi.test_reads_the_settings_record_with_the_token_and_none_when_missing"),
    ("a cut answer is unreadable", "service/app.py", "except (OSError, http.client.HTTPException, ValueError) as e:",
     "except (OSError, ValueError) as e:", S + "ShopApi.test_a_cut_answer_is_unreadable"),
    ("every item group is read, not one page", "service/app.py", 'optical.field_of(prefix)]), "limit_page_length": 0}), list)',
     'optical.field_of(prefix)]), "limit_page_length": 20}), list)', S + "ShopApi.test_reads_every_item_group_with_the_apps_mark"),
    ("only two fields of a prescription are asked for", "service/app.py", '"fields": json.dumps(["kind", "valid_until"]),',
     '"fields": json.dumps(["*"]),', S + "ShopApi.test_reads_only_two_fields_of_the_customers_prescriptions"),
    ("only the customer's prescriptions are read", "service/app.py", '"filters": json.dumps([["customer", "=", customer]]),',
     '"filters": json.dumps([]),', S + "ShopApi.test_reads_only_two_fields_of_the_customers_prescriptions"),
    ("a redirect is not followed", "service/app.py", "urllib.request.build_opener(_NoRedirect)", "urllib.request.build_opener()",
     S + "ShopApi.test_a_redirect_is_not_followed"),
    ("the function checks the signature too", "service/app.py", "    code, out = svc.handle(method, path, headers, raw)\n",
     "    code, out = (200, {'verdict': 'refuse'}) if path != '/health' else svc.handle(method, path, headers, raw)\n",
     S + "AsAFunction.test_health_a_signed_check_either_body_form_and_a_refusal"),
    # the manifest
    ("the integration role only reads the settings", "manifest.json",
     '"email": 0\n    }\n   ]\n  },\n  {\n   "name": "PP OPT Prescription"', '"email": 1\n    }\n   ]\n  },\n  {\n   "name": "PP OPT Prescription"',
     M + "test_the_integration_role_only_reads"),
    ("the check lets the sale go on when down", "manifest.json", '"down_answer": "allow_and_flag"', '"down_answer": "refuse"',
     M + "test_one_check_switched_off_that_lets_the_sale_go_on_when_down"),
    ("a remake unticks Ready to collect", "manifest.json", '"update_value": "0"', '"update_value": "1"',
     M + "test_the_workflow_ticks_ready_at_the_store_unticks_it_on_a_remake_and_closes_at_the_end"),
    ("Back from lab ticks Ready to collect", "manifest.json",
     '"state": "PP OPT Ready to collect",\n     "allow_edit": "Sales User",\n     "update_field": "ready_to_collect"',
     '"state": "PP OPT Ready to collect",\n     "allow_edit": "Sales User",\n     "update_field": "closed"',
     M + "test_the_workflow_ticks_ready_at_the_store_unticks_it_on_a_remake_and_closes_at_the_end"),
    ("an order ready to collect can be cancelled", "manifest.json",
     '"state": "PP OPT Ready to collect",\n     "action": "PP OPT Cancel",', '"state": "PP OPT Ordered",\n     "action": "PP OPT Cancel",',
     M + "test_the_workflow_ticks_ready_at_the_store_unticks_it_on_a_remake_and_closes_at_the_end"),
    ("a copied value is read only", "manifest.json", '"fetch_from": "prescription.r_sph",\n     "read_only": 1',
     '"fetch_from": "prescription.r_sph",\n     "read_only": 0', M + "test_a_lab_order_copies_its_prescription_read_only"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s42-canary-")
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
