#!/usr/bin/env python3
"""S58's canaries: each manifest test must go RED when the rule it guards is broken. For each mutation this copies the
sample (and the kit's checker it imports) to a temporary folder, runs the one test named on that unmutated copy (it must
pass, else BROKEN), applies ONE change to the manifest (the anchor must match exactly once, and the mutant must still
be JSON), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S57's
(`samples/s57_donation_intake/tests/canaries.py` @ 7503a3d, as S53 copies S33's; a defect there is a defect here).

    python3 samples/s58_repairs_by_serial/tests/canaries.py      # exit 0 only when every canary is RED
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
     '"received_on",\n    "ready_by"\n   ],\n   "filters"', '"received_on",\n    "ready_by",\n    "pp_rpr_nowhere"\n   ],\n   "filters"',
     T + "test_the_manifest_passes_the_kits_checker_with_no_warning"),
    ("the app calls no outside address", M, '"allowed_urls": [],', '"allowed_urls": ["https://partner.example/rpr"],',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("no money is held on the repair (the till charges it)", M,
     '"fieldname": "notes",\n     "fieldtype": "Small Text",', '"fieldname": "notes",\n     "fieldtype": "Currency",',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("Stock Entry's Repair is never required", M,
     '"insert_after": "stock_entry_type",', '"insert_after": "stock_entry_type",\n   "reqd": 1,',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("a submitted Material Issue can still name its repair", M,
     '   "allow_on_submit": 1,\n   "description": "The repair whose', '   "description": "The repair whose',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("Stock Entry's Repair shows on a Material Issue", M, '\\"Material Issue\\"', '\\"Material Receipt\\"',
     T + "test_no_outside_address_no_money_and_one_optional_field_on_stock_entry"),
    ("no step ticks a box (Duplicate would copy it)", M,
     '"state": "PP RPR Ready to collect",\n     "allow_edit": "Sales User"\n    },\n    {\n     "state": "PP RPR Collected"',
     '"state": "PP RPR Ready to collect",\n     "allow_edit": "Sales User",\n     "update_field": "notes",\n     "update_value": "1"\n    },\n    {\n     "state": "PP RPR Collected"',
     T + "test_no_tick_box_the_slip_reads_the_step"),
    ("the slip never decides by a field the API can set", M,
     '{% if state.endswith(\\" Ready to collect\\") or state.endswith(\\" Collected\\") %}', '{% if doc.work_done %}',
     T + "test_no_tick_box_the_slip_reads_the_step"),
    ("work begun is cancelled by a manager only", M,
     '"next_state": "PP RPR Cancelled",\n     "allowed": "Sales Manager",', '"next_state": "PP RPR Cancelled",\n     "allowed": "Sales User",',
     T + "test_the_repairs_moves_nothing_leaves_collected_and_a_manager_cancels_work_begun"),
    ("nothing leaves Collected", M,
     '"state": "PP RPR Ready to collect",\n     "action": "PP RPR Back to work",', '"state": "PP RPR Collected",\n     "action": "PP RPR Back to work",',
     T + "test_the_repairs_moves_nothing_leaves_collected_and_a_manager_cancels_work_begun"),
    ("the lock holds from Collected", M,
     '"states": [\n    "PP RPR Collected",\n    "PP RPR Cancelled"\n   ],', '"states": [\n    "PP RPR Cancelled"\n   ],',
     T + "test_the_lock_holds_every_field_the_slip_prints_once_collected"),
    ("the lock holds the tests the slip prints", M, '    "condition",\n    "tests",\n', '    "condition",\n',
     T + "test_the_lock_holds_every_field_the_slip_prints_once_collected"),
    ("the lock holds the date promised the slip prints", M, '    "received_on",\n    "ready_by",\n    "fault",', '    "received_on",\n    "fault",',
     T + "test_the_lock_holds_every_field_the_slip_prints_once_collected"),
    ("the lock never holds a fetched copy", M, '    "parts",\n    "sale"\n   ],', '    "parts",\n    "sale",\n    "customer_name"\n   ],',
     T + "test_the_lock_holds_every_field_the_slip_prints_once_collected"),
    ("a broken lock refuses, never only flags", M, '"kind": "locked_in_state",\n   "mode": "refuse",', '"kind": "locked_in_state",\n   "mode": "flag",',
     T + "test_the_lock_holds_every_field_the_slip_prints_once_collected"),
    ("the warranty date is a read-only copy of the serial's", M,
     '"fetch_from": "serial_no.warranty_expiry_date",\n     "read_only": 1,', '"fetch_from": "serial_no.warranty_expiry_date",',
     T + "test_what_is_read_from_the_serial_and_the_customer_is_a_read_only_copy"),
    ("the customer's phone is the till's own field", M, '"customer.custom_phone_no"', '"customer.mobile_no"',
     T + "test_what_is_read_from_the_serial_and_the_customer_is_a_read_only_copy"),
    ("Open repairs leaves out collected repairs", M,
     '"not in",\n     [\n      "PP RPR Collected",\n      "PP RPR Cancelled"\n     ]', '"not in",\n     [\n      "PP RPR Cancelled"\n     ]',
     T + "test_open_repairs_lists_those_not_collected_by_the_date_promised"),
    ("no table is ever required", M,
     '"fieldname": "parts",\n     "fieldtype": "Table",', '"fieldname": "parts",\n     "reqd": 1,\n     "fieldtype": "Table",',
     T + "test_no_table_is_ever_required"),
    ("a blank test row is never printed", M, "{% for t in doc.tests if t.test %}", "{% for t in doc.tests %}",
     T + "test_the_slip_reads_only_fields_that_exist_and_shows_the_work_once_ready"),
    ("the slip reads only fields that exist", M, '{{ t.reading or \\"\\" }}', '{{ t.value or \\"\\" }}',
     T + "test_the_slip_reads_only_fields_that_exist_and_shows_the_work_once_ready"),
    ("the slip prints under the retailer's letter head", M,
     '{% if letter_head and not no_letterhead %}<div class=\\"letter-head\\">{{ letter_head }}</div>{% endif %}\\n', '',
     T + "test_the_slip_reads_only_fields_that_exist_and_shows_the_work_once_ready"),
    ("a serial number lists its repairs", M, '"doctype": "Serial No",\n   "link_doctype"', '"doctype": "Batch",\n   "link_doctype"',
     T + "test_the_serial_the_customer_and_the_sale_list_their_repairs"),
    ("store staff cannot delete a repair", M,
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 0,',
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,',
     T + "test_store_staff_keep_repairs_no_one_but_a_system_manager_deletes_and_stock_reads"),
    ("a manager cancels a repair, never deletes it", M,
     '"role": "Sales Manager",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 0,',
     '"role": "Sales Manager",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,',
     T + "test_store_staff_keep_repairs_no_one_but_a_system_manager_deletes_and_stock_reads"),
    ("Stock User only reads", M,
     '"role": "Stock User",\n     "read": 1,\n     "write": 0,', '"role": "Stock User",\n     "read": 1,\n     "write": 1,',
     T + "test_store_staff_keep_repairs_no_one_but_a_system_manager_deletes_and_stock_reads"),
    ("the repair opens its help", M, "repairs_by_serial.html#repairs", "repairs_by_serial.html",
     T + "test_the_repair_opens_its_help"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s58-canary-")
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
