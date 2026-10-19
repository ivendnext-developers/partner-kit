#!/usr/bin/env python3
"""S30's canaries: each guard on the migration and on the units report must go RED when the rule it guards is broken.
For each mutation this copies the sample (and the feed client it imports) to a temporary folder, runs the one test named
on that unmutated copy (it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the
mutant must compile), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is
S26's (`samples/s26_derived_prices/tests/canaries.py` @ b40adfa; a defect there is a defect here).

    python3 samples/s30_units_as_serials/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
U = "units.py"

CANARIES = [
    # the migration
    ("run twice: a code already moved is not received again", U,
     '            else:\n                out["moved"].append({"code": code, "why": "already moved"})\n            continue',
     '            else:\n                out["moved"].append({"code": code, "why": "already moved"})',
     "test_units.Plan.test_a_code_already_moved_is_not_planned_again"),
    ("one code, one item: a code on another item is never received", U,
     "        if have:\n", "        if have and have.get('item_code') == new_item:\n",
     "test_units.Migrate.test_a_code_already_on_another_item_is_never_made_twice"),
    ("a lot with a conflicting code is not counted to 0", U, '        if (item, store, batch) in plan["blocked"]:',
     "        if False:", "test_units.Migrate.test_a_code_already_on_another_item_is_never_made_twice"),
    ("a lot with packs without a code is held", U, "        if qty != want:", "        if False:",
     "test_units.Plan.test_a_lot_with_packs_without_a_code_is_held"),
    ("two codes differing only in case collide", U, "        key = code.upper()", "        key = code",
     "test_units.Plan.test_two_codes_that_differ_only_in_case_collide"),
    # the units report
    ("a unit present at the count is in stock, not counted out", U, '    if status == "Delivered":',
     '    if status == "Delivered" or (last_out and last_out.get("voucher_type") == COUNT):',
     "test_units.Classify.test_a_unit_present_at_the_count_is_in_stock"),
    ("a till sale after a count is sold, not counted out (the LATEST outward movement)", U,
     "    last_out = outs[-1] if outs else None",
     "    last_out = next((m for m in outs if m.get('voucher_type') == COUNT), outs[-1] if outs else None)",
     "test_units.Classify.test_a_sale_after_a_count_is_sold_not_counted_out"),
    ("a time is read as numbers: 9:30 comes before 14:00", U,
     '    return (str(m.get("posting_date") or ""), _clock(m.get("posting_time")), str(m.get("creation") or ""))',
     '    return (str(m.get("posting_date") or ""), str(m.get("posting_time") or ""), str(m.get("creation") or ""))',
     "test_units.Classify.test_a_morning_sale_and_return_then_an_afternoon_count_is_counted_out"),
    ("a code whose receipt was cancelled is received again, never counted as moved", U,
     "            have = None     # its receipt", "            pass     # its receipt",
     "test_units.Plan.test_a_code_whose_receipt_was_cancelled_is_received_again"),
    ("the receipt posts where the count to 0 posts", "migrate.py", '"expense_account": account,', "",
     "test_units.Migrate.test_a_run_moves_the_units_and_counts_the_old_item_to_zero"),
    ("--remove touches only what this script made", "apply_config.py",
     '        made("Warehouse", doc["name"])\n', "",
     "test_config.Config.test_twice_then_remove_puts_the_shop_back"),
    ("--remove touches only what this script made (a record already there)", "apply_config.py",
     '    for dt, name in reversed(before["made"]):', '    for dt, name in reversed(before["made"] + [["Warehouse", n] for n in defective_names(shop, conf)]):',
     "test_config.Config.test_a_record_already_in_the_shop_is_never_touched_by_remove"),
    ("movements are judged in time order", U, "    moves = sorted(movements, key=_when)", "    moves = list(reversed(movements))",
     "test_units.Classify.test_a_sale_after_a_count_is_sold_not_counted_out"),
]
def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s30-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("state", "__pycache__"))
        for tool in ("feed_client", "manifest"):
            shutil.copytree(os.path.join(kit, "tools", tool), os.path.join(tmp, "r", "tools", tool),
                            ignore=shutil.ignore_patterns("__pycache__"))
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
