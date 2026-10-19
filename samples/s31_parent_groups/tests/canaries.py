#!/usr/bin/env python3
"""S31's canaries: each ownership and offer guard must go RED when the rule it guards is broken. For each mutation this
copies the sample (and the feed client it imports) to a temporary folder, runs the one test named on that unmutated copy
(it must pass, else BROKEN), applies ONE change (the anchor must match exactly once, and the mutant must compile), runs
the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S26's
(`samples/s26_derived_prices/tests/canaries.py` @ b40adfa; a defect there is a defect here).

    python3 samples/s31_parent_groups/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import os
import py_compile
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G = "groups.py"

CANARIES = [
    ("a person's own row is never removed (ownership is the service's own list, not a guess from the tree)", G,
     "        for (t, child) in sorted(out[\"mine\"]):\n            if t == table and child not in wanted and child in present:\n"
     "                out[\"drop\"].setdefault(table, []).append(child)\n                del out[\"mine\"][(t, child)]",
     "        for (t, child) in sorted({(table, c) for c in present} | set(out[\"mine\"])):\n"
     "            if t == table and child not in wanted and child in present and child not in {p[key] for p in parents}:\n"
     "                out[\"drop\"].setdefault(table, []).append(child)\n                out[\"mine\"].pop((t, child), None)",
     "test_groups.Service.test_a_persons_row_survives_the_parent_being_removed"),
    ("a row a person already has is not claimed as ours", G,
     "            if (table, child) not in out[\"mine\"] and child not in present and (table, child) not in out[\"removed\"]:",
     "            if (table, child) not in out[\"mine\"] and (table, child) not in out[\"removed\"]:",
     "test_groups.Plan.test_a_persons_own_child_row_is_not_added_again_nor_claimed"),
    ("a promotion's buy or get row is never written out", G,
     '    PROMOTION: {"table_promotion_exclusion_list": ("source_type", "source", ())},',
     '    PROMOTION: {"table_promotion_exclusion_list": ("source_type", "source", ()), "table_buy_items": ("source_type", "source_key", ())},',
     "test_groups.Plan.test_a_promotion_buy_or_get_parent_is_flagged_never_written_out"),
    ("a row a person removed is not added back", G, "                del out[\"mine\"][(t, child)]\n                out[\"removed\"].add((t, child))",
     "                del out[\"mine\"][(t, child)]", "test_groups.Plan.test_a_row_a_person_removed_is_not_added_back"),
    ("every descendant, not only the children", G, "        todo += sorted(kids.get(g, []))", "        pass",
     "test_groups.Plan.test_a_coupon_parent_row_gets_every_child_with_its_discount"),
    ("a child another listed parent still covers is kept", G,
     "            if t == table and child not in wanted and child in present:",
     "            if t == table and out[\"mine\"][(t, child)] not in {p[key] for p in parents} and child in present:",
     "test_groups.Plan.test_removing_the_parent_drops_only_the_rows_the_service_added"),
    ("a group moved out from under the parent is dropped", G,
     "            if t == table and child not in wanted and child in present:", "            if False:",
     "test_groups.Plan.test_a_group_moved_out_from_under_the_parent_is_dropped"),
    ("a removed child comes back when its parent is listed again", G,
     '        out["removed"] = {(t, c) for (t, c) in out["removed"] if t != table or c in wanted}', "        pass",
     "test_groups.Plan.test_a_removed_child_comes_back_when_its_parent_is_listed_again"),
    ("one refused record does not roll back the others' store rows", "expander.py",
     '                db.execute("rollback to one_record")', "                raise",
     "test_groups.Service.test_a_refused_record_rolls_back_only_itself"),
]
def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s31-canary-")
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
