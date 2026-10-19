#!/usr/bin/env python3
"""S33's canaries: each manifest test must go RED when the rule it guards is broken. For each mutation this copies the
sample (and the kit's checker it imports) to a temporary folder, runs the one test named on that unmutated copy (it must
pass, else BROKEN), applies ONE change to the manifest (the anchor must match exactly once, and the mutant must still
be JSON), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S31's
(`samples/s31_parent_groups/tests/canaries.py` @ 90a8832; a defect there is a defect here).

    python3 samples/s33_click_and_collect/tests/canaries.py      # exit 0 only when every canary is RED
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
M = "manifest.json"
T = "test_manifest.ManifestTest."

CANARIES = [
    ("the hand-over can be set on a submitted note", M,
     '"insert_after": "po_no",\n   "allow_on_submit": 1,', '"insert_after": "po_no",',
     T + "test_the_two_fields_are_on_the_delivery_note_and_settable_after_submit"),
    ("Handed over is a list filter (the waiting list)", M, '   "in_standard_filter": 1,\n', "",
     T + "test_handed_over_is_a_list_column_and_a_list_filter_so_the_list_is_the_waiting_list"),
    ("the pick list is only orders still to deliver", M,
     '["status", "in", ["To Deliver and Bill", "To Deliver"]],', '["status", "in", ["To Deliver and Bill", "To Deliver", "Completed"]],',
     T + "test_web_orders_to_pick_are_submitted_sales_orders_still_to_deliver_with_a_web_order_number"),
    ("the pick list is only web orders", M,
     '["status", "in", ["To Deliver and Bill", "To Deliver"]],\n    ["po_no", "is", "set"]',
     '["status", "in", ["To Deliver and Bill", "To Deliver"]]',
     T + "test_web_orders_to_pick_are_submitted_sales_orders_still_to_deliver_with_a_web_order_number"),
    ("no report names a field this manifest adds (the shop refuses it)", M,
     '"columns": ["name", "customer_name", "set_warehouse", "delivery_date", "po_no", "status"],',
     '"columns": ["name", "customer_name", "set_warehouse", "delivery_date", "po_no", "status", "pp_ccb_handed_over"],',
     T + "test_no_report_names_a_field_this_manifest_adds"),
    ("the workspace opens the delivery notes", M,
     ',\n    {"type": "DocType", "link_to": "Delivery Note", "label": "Delivery notes"}', "",
     T + "test_the_workspace_opens_the_two_lists_and_never_its_own_report"),
    ("the workspace's line names the report to search for", M, "search Desk for Web orders to pick", "search Desk for the pick list",
     T + "test_the_workspace_opens_the_two_lists_and_never_its_own_report"),
    ("nothing leaves the shop", M, '"allowed_urls": [],', '"allowed_urls": ["https://partner.example/ccb"],',
     T + "test_nothing_leaves_the_shop"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s33-canary-")
    try:
        kit = os.path.dirname(os.path.dirname(ROOT))
        dest = os.path.join(tmp, "r", "samples", os.path.basename(ROOT))
        shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copytree(os.path.join(kit, "tools", "manifest"), os.path.join(tmp, "r", "tools", "manifest"),
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
        json.loads(open(f).read())       # the mutant is still a manifest the test can read
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
