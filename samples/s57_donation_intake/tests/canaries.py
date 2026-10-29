#!/usr/bin/env python3
"""S57's canaries: each manifest test must go RED when the rule it guards is broken. For each mutation this copies the
sample (and the kit's checker it imports) to a temporary folder, runs the one test named on that unmutated copy (it must
pass, else BROKEN), applies ONE change to the manifest (the anchor must match exactly once, and the mutant must still
be JSON), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S33's
(`samples/s33_click_and_collect/tests/canaries.py` @ 20e2c5d, as S53 copies it; a defect there is a defect here).

    python3 samples/s57_donation_intake/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("the retailer's install refuses nothing (a report on a missing field)", M,
     '"customer",\n    "receipt_given"\n   ],', '"customer",\n    "receipt_given",\n    "pp_don_nowhere"\n   ],',
     T + "test_the_manifest_passes_the_kits_checker_with_no_warning"),
    ("the app calls no outside address", M, '"allowed_urls": [],', '"allowed_urls": ["https://partner.example/don"],',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("no money is held on the donation (the receipt states no value)", M,
     '"fieldname": "notes",\n     "fieldtype": "Small Text",', '"fieldname": "notes",\n     "fieldtype": "Currency",',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("Stock Entry's Donation is never required", M,
     '"insert_after": "stock_entry_type",', '"insert_after": "stock_entry_type",\n   "reqd": 1,',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("a submitted Material Receipt can still name its donation", M,
     '   "allow_on_submit": 1,\n   "description": "The donation whose', '   "description": "The donation whose',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("Give receipt ticks Receipt given", M,
     '"update_field": "receipt_given",\n     "update_value": "1"', '"update_field": "receipt_given",\n     "update_value": "0"',
     T + "test_give_receipt_ticks_receipt_given_and_cancel_ticks_cancelled"),
    ("Receipt given is ticked only by the workflow", M,
     '"label": "Receipt given",\n     "read_only": 1,', '"label": "Receipt given",',
     T + "test_give_receipt_ticks_receipt_given_and_cancel_ticks_cancelled"),
    ("a given receipt is cancelled by a manager only", M,
     '"next_state": "PP DON Cancelled",\n     "allowed": "Sales Manager",', '"next_state": "PP DON Cancelled",\n     "allowed": "Sales User",',
     T + "test_a_given_receipt_is_cancelled_by_a_manager_only_and_nothing_leaves_cancelled"),
    ("nothing leaves Cancelled", M,
     '"state": "PP DON Received",\n     "action": "PP DON Give receipt",', '"state": "PP DON Cancelled",\n     "action": "PP DON Give receipt",',
     T + "test_a_given_receipt_is_cancelled_by_a_manager_only_and_nothing_leaves_cancelled"),
    ("the lock holds from Receipt given", M,
     '"states": [\n    "PP DON Receipt given",\n    "PP DON Cancelled"\n   ],', '"states": [\n    "PP DON Cancelled"\n   ],',
     T + "test_the_lock_holds_every_field_the_receipt_prints_once_it_is_given"),
    ("the lock holds the goods the receipt prints", M, '    "received_on",\n    "goods"\n   ],', '    "received_on"\n   ],',
     T + "test_the_lock_holds_every_field_the_receipt_prints_once_it_is_given"),
    ("the lock holds the donor's address the receipt prints", M, '    "donor_address",\n    "store",', '    "store",',
     T + "test_the_lock_holds_every_field_the_receipt_prints_once_it_is_given"),
    ("a broken lock refuses, never only flags", M, '"kind": "locked_in_state",\n   "mode": "refuse",', '"kind": "locked_in_state",\n   "mode": "flag",',
     T + "test_the_lock_holds_every_field_the_receipt_prints_once_it_is_given"),
    ("a walk-up donor can type a name", M,
     '"fetch_from": "customer.customer_name",', '"fetch_from": "customer.customer_name",\n     "read_only": 1,',
     T + "test_the_donors_details_come_from_the_customer_and_can_be_typed"),
    ("Donations leaves out cancelled donations", M,
     '"filters": [\n    [\n     "cancelled",\n     "=",\n     0\n    ]\n   ],', '"filters": [],',
     T + "test_donations_lists_those_not_cancelled_newest_first"),
    ("Cancelled is never a standard filter (Desk would drop the report's saved filter)", M,
     '"label": "Cancelled",\n     "read_only": 1,', '"label": "Cancelled",\n     "read_only": 1,\n     "in_standard_filter": 1,',
     T + "test_donations_lists_those_not_cancelled_newest_first"),
    ("the goods table is never required", M,
     '"fieldname": "goods",\n     "fieldtype": "Table",', '"fieldname": "goods",\n     "reqd": 1,\n     "fieldtype": "Table",',
     T + "test_the_goods_table_is_never_required"),
    ("a blank row of goods is never printed", M,
     "{% for g in doc.goods if g.category or g.description %}", "{% for g in doc.goods %}",
     T + "test_the_receipt_reads_only_fields_that_exist_and_states_no_value"),
    ("the receipt reads only fields that exist", M, '{{ g.category or \\"\\" }}', '{{ g.kind or \\"\\" }}',
     T + "test_the_receipt_reads_only_fields_that_exist_and_states_no_value"),
    ("the receipt states no value", M, " This receipt describes the goods and states no value.", "",
     T + "test_the_receipt_reads_only_fields_that_exist_and_states_no_value"),
    ("a customer lists its donations", M, '"doctype": "Customer",\n   "link_doctype"', '"doctype": "Supplier",\n   "link_doctype"',
     T + "test_a_customer_lists_its_donations"),
    ("store staff cannot delete a donation", M,
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 0,',
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,',
     T + "test_store_staff_take_donations_managers_delete_and_stock_reads"),
    ("Stock User only reads", M,
     '"role": "Stock User",\n     "read": 1,\n     "write": 0,', '"role": "Stock User",\n     "read": 1,\n     "write": 1,',
     T + "test_store_staff_take_donations_managers_delete_and_stock_reads"),
    ("the donation opens its help", M, "donation_intake.html#donations", "donation_intake.html",
     T + "test_the_donation_opens_its_help"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s57-canary-")
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
