#!/usr/bin/env python3
"""S62's canaries: each test that guards a retailer's secret or key, the ledger rows read (the store's own, not cancelled,
inside the period), each movement's line, the balance from the last ledger row, the count difference, the litres and
strength, the unit, the rounding, a return never written over, the press's time, or the service's words must go RED when
that check is removed. For each mutation this copies the sample (and the kit folders it uses) to a temporary folder, runs
the one test named on the unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly
once, and the mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The
runner is S16's, by way of S44's and S61's.

    python3 samples/s62_liquor_excise_returns/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
T, M, R, S, C = "test_service.ServiceTest.", "test_many_shops.ManyShops.", "test_rules.", "service/app.py", "exr.py"
S1 = T + "test_s1_work_out_writes_twelve_lines_per_class_from_the_stores_ledger"

CANARIES = [
    ("the signature is checked", S, "        if not secrets or all(exr.verify(ts, sig, raw, s) for s in secrets):",
     "        if not secrets:", T + "test_s10_a_bad_signature_another_secret_and_an_old_stamp_are_refused"),
    ("an old stamp is refused", C, " or abs((now or time.time()) - int(ts)) > SKEW_S:", ":",
     T + "test_s10_a_bad_signature_another_secret_and_an_old_stamp_are_refused"),
    ("a long timestamp is refused", C, " and len(ts) <= 20)", ")",
     T + "test_s8b_another_417_is_not_called_a_rights_problem_and_a_long_timestamp_is_refused"),
    ("a 417 is a rights problem only by its kind", S, " or (e.code == 417 and e.kind in RIGHTS_KINDS)", " or e.code == 417",
     T + "test_s8b_another_417_is_not_called_a_rights_problem_and_a_long_timestamp_is_refused"),
    ("a refused user is named in words", S, "            if e.code in (401, 403) or (e.code == 417 and e.kind in RIGHTS_KINDS):",
     "            if False:", T + "test_s8_the_apps_user_refused_by_the_site_is_said_in_words"),
    ("Administrator's key is never used", S, ' and k != "user:Administrator")', ")", M + "test_administrators_key_is_never_used"),
    ("a press before the site's key arrives is answered in words", S,
     "        if door is None:\n            return 200, _warning(NOT_SET_UP)\n", "",
     M + "test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing"),
    ("only a draft is worked out", S, "        if (r.get(\"workflow_state\") or exr.DRAFT) != exr.DRAFT:", "        if False:",
     T + "test_s5_only_a_draft_with_a_store_a_period_and_a_unit_is_worked_out"),
    ("the period is checked", C, "    if b < a:\n", "    if False:\n",
     T + "test_s5_only_a_draft_with_a_store_a_period_and_a_unit_is_worked_out"),
    ("a write carries the modified it read", S, '\n                                            "modified": r.get("modified")})', "})",
     T + "test_s6_a_return_saved_meanwhile_is_never_written_over"),
    ("nothing is written past the press's time", S, "        self.left(t0)                   # out of time after the reads",
     "        pass                   # out of time after the reads", T + "test_s7b_reads_done_but_the_time_gone_writes_nothing"),
    ("only the store's own rows", S, '        span = [["warehouse", "=", store], ', "        span = [",
     S1),
    ("never a cancelled row", S, '["is_cancelled", "=", 0], ["posting_datetime", ">=", start]', '["posting_datetime", ">=", start]',
     S1),
    ("not before the period", S, ' ["posting_datetime", ">=", start],\n', "\n", S1),
    ("not after the period", S, '                ["posting_datetime", "<", end]]', "                ]", S1),
    ("the opening's balance is the store's own", S, '        base = [["warehouse", "=", store], ["is_cancelled", "=", 0]]',
     '        base = [["is_cancelled", "=", 0]]', S1),
    ("the last row at the item's last time wins", C, "        if qty is not None and (item not in best or key > best[item][0]):",
     "        if qty is not None and (item not in best or key < best[item][0]):", R + "Balances.test_the_last_row_at_the_items_last_time_by_creation"),
    ("only the item's own last time", C, " or moment(r.get(\"posting_datetime\")) != last[item]:", ":",
     R + "Balances.test_the_last_row_at_the_items_last_time_by_creation"),
    ("a sale is Sold", C, "        return RETURNED_IN if inward else SOLD", "        return RETURNED_IN if inward else OTHER_OUT",
     R + "Kinds.test_each_voucher_type_and_purpose_has_its_line"),
    ("a supplier return is its own line", C, "        return RECEIVED if inward else RETURNED_OUT",
     "        return RECEIVED if inward else SOLD", R + "Kinds.test_each_voucher_type_and_purpose_has_its_line"),
    ("a Material Issue is written off", C, '        if purpose == "Material Issue" and not inward:', "        if False:",
     R + "Kinds.test_each_voucher_type_and_purpose_has_its_line"),
    ("counts and entries are not read by voucher type", C, ' and r.get("voucher_type") not in SKIPPED:', ":",
     R + "WorkOut.test_counts_and_entries_are_never_read_from_the_voucher_type_totals"),
    ("an entry nets per entry", C, "            nets[key] = nets.get(key, Decimal(0)) + qty", "            nets[(key, qty)] = qty",
     R + "WorkOut.test_stock_entries_net_per_entry_and_by_purpose"),
    ("the count difference is what is left, of the rounded lines", C,
     '        for col in ("units", "volume", "pure_alcohol"):   # the count', '        for col in ():   # the count',
     R + "WorkOut.test_each_printed_column_adds_up_after_rounding"),
    ("a read's values stay within their bytes", S, "        if chunk and size + n > CHUNK_BYTES:", "        if False:",
     T + "test_s4b_reads_stay_short_for_a_store_of_many_items"),
    ("a store with no ledger is refused, never an empty return", S,
     "        if items and not held:", "        if False:",
     T + "test_s4_a_store_with_no_ledger_is_refused_and_one_with_no_liquor_says_so"),
    ("an item without a class is left out", C, "        if item in items and qty:", "        if qty:",
     R + "WorkOut.test_items_without_a_class_or_any_figure_are_left_out"),
    ("pure alcohol is volume times strength", C, '            t[2] += vol * (it["abv"] or Decimal(0)) / 100',
     "            t[2] += vol", R + "WorkOut.test_a_count_is_what_is_left_and_the_figures_close"),
    ("millilitres become litres", C, "    litres = ml / 1000 if", "    litres = ml if",
     R + "Items.test_millilitres_to_litres_and_the_bounds"),
    ("a strength above 100 is refused", C, " and 0 < abv <= 100 else None", " else None",
     R + "Items.test_millilitres_to_litres_and_the_bounds"),
    ("US gallons", C, '    scale = Decimal(1) if unit == "Litres" else 1 / GALLON', "    scale = Decimal(1)",
     T + "test_s3_us_gallons"),
    ("rounded once per line, half up", C, "    return v.quantize(PLACES, rounding=ROUND_HALF_UP)", "    return v.quantize(PLACES)",
     R + "WorkOut.test_us_gallons_and_rounding_once_per_line_half_up"),
    ("an item missing litres or strength is named", C, '        if it["litres"] is None or it["abv"] is None:', "        if False:",
     R + "WorkOut.test_missing_litres_or_strength_counts_units_and_names_the_item"),
    ("the whole summary", C, '            f"closing stock {_sum(lines, CLOSING, \'volume\'):,.3f} {u}.")',
     '            f"closing stock {_sum(lines, OPENING, \'volume\'):,.3f} {u}.")', R + "Words.test_the_summary_in_full"),
    ("a count change is said", C, '    if _sum(lines, COUNT, "units"):', "    if False:", S1),
    ("the read of the items asks for its three fields only", S,
     '            "Item", ["name", "item_name", exr.FIELD + "class", exr.FIELD + "ml", exr.FIELD + "abv"],',
     '            "Item", ["name", "item_name", "item_group", exr.FIELD + "class", exr.FIELD + "ml", exr.FIELD + "abv"],',
     T + "test_s2_the_reads_are_few_and_never_a_row_a_sale"),
    ("the class code rides the line", C, '"return_code": (codes or {}).get(cls) or "",', '"return_code": "",',
     R + "WorkOut.test_the_class_code_rides_each_line"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s62-canary-")
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
