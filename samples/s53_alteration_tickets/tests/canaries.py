#!/usr/bin/env python3
"""S53's canaries: each manifest test must go RED when the rule it guards is broken. For each mutation this copies the
sample (and the kit's checker it imports) to a temporary folder, runs the one test named on that unmutated copy (it must
pass, else BROKEN), applies ONE change to the manifest (the anchor must match exactly once, and the mutant must still
be JSON), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S33's
(`samples/s33_click_and_collect/tests/canaries.py` @ 20e2c5d; a defect there is a defect here).

    python3 samples/s53_alteration_tickets/tests/canaries.py      # exit 0 only when every canary is RED
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
     '"tailor",\n    "ready_to_collect"\n   ],', '"tailor",\n    "ready_to_collect",\n    "pp_alt_nowhere"\n   ],',
     T + "test_the_manifest_passes_the_kits_checker_with_no_warning"),
    ("the app calls no outside address", M, '"allowed_urls": [],', '"allowed_urls": ["https://partner.example/alt"],',
     T + "test_no_outside_address_and_no_money_is_held"),
    ("no money is held on the ticket", M,
     '"fieldname": "notes",\n     "fieldtype": "Small Text",', '"fieldname": "notes",\n     "fieldtype": "Currency",',
     T + "test_no_outside_address_and_no_money_is_held"),
    ("Ready ticks Ready to collect", M,
     '"state": "PP ALT Ready to collect",\n     "allow_edit": "Sales User",\n     "update_field": "ready_to_collect",\n     "update_value": "1"',
     '"state": "PP ALT Ready to collect",\n     "allow_edit": "Sales User",\n     "update_field": "ready_to_collect",\n     "update_value": "0"',
     T + "test_ready_ticks_ready_to_collect_and_going_back_unticks_it"),
    ("a fitting unticks Ready to collect", M,
     '"state": "PP ALT Fitting",\n     "allow_edit": "Sales User",\n     "update_field": "ready_to_collect",\n     "update_value": "0"',
     '"state": "PP ALT Fitting",\n     "allow_edit": "Sales User"',
     T + "test_ready_ticks_ready_to_collect_and_going_back_unticks_it"),
    ("Hand over closes the ticket", M,
     '"state": "PP ALT Handed over",\n     "allow_edit": "System Manager",\n     "update_field": "closed",',
     '"state": "PP ALT Handed over",\n     "allow_edit": "System Manager",\n     "update_field": "ready_to_collect",',
     T + "test_hand_over_and_cancel_close_the_ticket_and_leave_it_to_a_system_manager"),
    ("a closed ticket is left to a System Manager", M,
     '"state": "PP ALT Cancelled",\n     "allow_edit": "System Manager",', '"state": "PP ALT Cancelled",\n     "allow_edit": "Sales User",',
     T + "test_hand_over_and_cancel_close_the_ticket_and_leave_it_to_a_system_manager"),
    ("the phone is the customer's, read only", M,
     '"fetch_from": "customer.custom_phone_no",\n     "read_only": 1,', '"fetch_from": "customer.custom_phone_no",',
     T + "test_the_phone_and_e_mail_are_the_customers_read_only"),
    ("Tickets Due lists open tickets only", M,
     '"filters": [\n    [\n     "closed",\n     "=",\n     0\n    ]\n   ],', '"filters": [],',
     T + "test_tickets_due_lists_open_tickets_by_ready_by"),
    ("Closed is never a standard filter (Desk would drop the report's saved filter)", M,
     '"fieldname": "closed",\n     "fieldtype": "Check",\n     "label": "Closed",\n     "read_only": 1,',
     '"fieldname": "closed",\n     "fieldtype": "Check",\n     "label": "Closed",\n     "read_only": 1,\n     "in_standard_filter": 1,',
     T + "test_tickets_due_lists_open_tickets_by_ready_by"),
    ("a child table is never required", M,
     '"fieldname": "garments",\n     "fieldtype": "Table",', '"fieldname": "garments",\n     "reqd": 1,\n     "fieldtype": "Table",',
     T + "test_child_tables_are_never_required"),
    ("the tag prints the ticket number", M, '22pt; font-weight: bold;\\">{{ doc.name }}', '22pt; font-weight: bold;\\">{{ doc.kind }}',
     T + "test_the_slip_and_tag_read_only_fields_that_exist"),
    ("the slip reads only fields that exist", M, '{{ g.work or \\"\\" }}', '{{ g.alteration or \\"\\" }}',
     T + "test_the_slip_and_tag_read_only_fields_that_exist"),
    ("a sale lists its tickets", M, '"doctype": "POS Invoice",', '"doctype": "Customer",',
     T + "test_the_customer_the_sale_and_the_order_list_their_tickets"),
    ("store staff cannot delete a ticket", M,
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 0,',
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,',
     T + "test_store_staff_work_tickets_and_only_managers_delete"),
    ("a blank measurement row is never printed", M, "{% for m in doc.measurements if m.measure %}", "{% for m in doc.measurements %}",
     T + "test_the_slip_and_tag_read_only_fields_that_exist"),
    ("the ticket opens its help", M, "alteration_tickets.html#tickets", "alteration_tickets.html",
     T + "test_the_ticket_opens_its_help"),
]


def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s53-canary-")
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
