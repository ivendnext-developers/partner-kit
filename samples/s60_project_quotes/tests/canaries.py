#!/usr/bin/env python3
"""S60's canaries: each manifest test must go RED when the rule it guards is broken. For each mutation this copies the
sample (and the kit's checker it imports) to a temporary folder, runs the one test named on that unmutated copy (it must
pass, else BROKEN), applies ONE change to the manifest (the anchor must match exactly once, and the mutant must still
be JSON), runs the test again, and reports RED (the test caught it) or GREEN (a dead test). The runner is S58's
(`samples/s58_repairs_by_serial/tests/canaries.py` @ f61ce0e, as S58 copies S57's; a defect there is a defect here).

    python3 samples/s60_project_quotes/tests/canaries.py      # exit 0 only when every canary is RED
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
    ("the retailer's install refuses nothing (a raw database read in the sheet)", M,
     '{{ doc.notes }}', '{{ db.sql(1) }}',
     T + "test_the_manifest_passes_the_kits_checker_with_no_warning"),
    ("the app calls no outside address", M, '"allowed_urls": [],', '"allowed_urls": ["https://partner.example/pqt"],',
     T + "test_no_outside_address_no_money_no_rule_of_its_own"),
    ("no money is held on the project (the till and the ERP keep it)", M,
     '"fieldname": "site_phone",\n     "fieldtype": "Data",', '"fieldname": "site_phone",\n     "fieldtype": "Currency",',
     T + "test_no_outside_address_no_money_no_rule_of_its_own"),
    ("the project is never required on an order", M,
     '"dt": "Sales Order",\n   "fieldname": "pp_pqt_project",', '"dt": "Sales Order",\n   "reqd": 1,\n   "fieldname": "pp_pqt_project",',
     T + "test_the_project_field_is_one_optional_link_on_the_five_documents_carried_by_create"),
    ("Create copies the project (never no_copy)", M,
     '"dt": "Delivery Note",\n   "fieldname": "pp_pqt_project",', '"dt": "Delivery Note",\n   "no_copy": 1,\n   "fieldname": "pp_pqt_project",',
     T + "test_the_project_field_is_one_optional_link_on_the_five_documents_carried_by_create"),
    ("one name on every document, or Create does not carry it", M,
     '"dt": "Sales Invoice",\n   "fieldname": "pp_pqt_project",', '"dt": "Sales Invoice",\n   "fieldname": "pp_pqt_project_si",',
     T + "test_the_project_field_is_one_optional_link_on_the_five_documents_carried_by_create"),
    ("a booked till sale can still be named to its project", M,
     '"dt": "POS Invoice",\n   "fieldname": "pp_pqt_project",\n   "fieldtype": "Link",\n   "label": "Project",\n   "options": "PP PQT Project",\n   "insert_after": "customer_name",\n   "allow_on_submit": 1,',
     '"dt": "POS Invoice",\n   "fieldname": "pp_pqt_project",\n   "fieldtype": "Link",\n   "label": "Project",\n   "options": "PP PQT Project",\n   "insert_after": "customer_name",',
     T + "test_the_project_field_is_one_optional_link_on_the_five_documents_carried_by_create"),
    ("a submitted order's line can be restaged", M,
     'Optional; carried to the order and each delivery.",\n   "allow_on_submit": 1\n', 'Optional; carried to the order and each delivery."\n',
     T + "test_the_stage_field_is_one_optional_text_field_on_the_three_line_tables"),
    ("the stage is on the delivery's lines too", M,
     '"dt": "Delivery Note Item",', '"dt": "Delivery Note Item Missing",',
     T + "test_the_stage_field_is_one_optional_text_field_on_the_three_line_tables"),
    ("the builder's name is a read-only copy", M,
     '"fetch_from": "customer.customer_name",\n     "read_only": 1', '"fetch_from": "customer.customer_name"',
     T + "test_the_builder_is_required_and_its_name_a_read_only_copy"),
    ("the builder is required", M,
     '"label": "Builder",\n     "options": "Customer",\n     "reqd": 1,', '"label": "Builder",\n     "options": "Customer",',
     T + "test_the_builder_is_required_and_its_name_a_read_only_copy"),
    ("the stages planned are never required", M,
     '"fieldname": "stages",\n     "fieldtype": "Table",', '"fieldname": "stages",\n     "reqd": 1,\n     "fieldtype": "Table",',
     T + "test_no_table_is_ever_required"),
    ("the sheet lists the invoices", M,
     'ivn_rows(\\"Sales Invoice\\", filters={\\"pp_pqt_project\\": doc.name}', 'ivn_rows(\\"Sales Invoice\\", filters={\\"customer\\": doc.customer}',
     T + "test_the_sheet_reads_each_document_with_the_viewers_rights_filtered_on_the_project"),
    ("the sheet never reads past the viewer's rights", M,
     'ivn_rows(\\"Quotation\\", filters={\\"pp_pqt_project\\": doc.name}', 'get_all(\\"Quotation\\", filters={\\"pp_pqt_project\\": doc.name}',
     T + "test_the_sheet_reads_each_document_with_the_viewers_rights_filtered_on_the_project"),
    ("the sheet places the retailer's letter head", M,
     '{% if letter_head and not no_letterhead %}<div class=\\"letter-head\\">{{ letter_head }}</div>{% endif %}\\n', '',
     T + "test_the_sheet_reads_each_document_with_the_viewers_rights_filtered_on_the_project"),
    ("the sheet reads only the project's own fields", M,
     '{{ doc.project_name }} ·', '{{ doc.project_title }} ·',
     T + "test_the_sheet_reads_each_document_with_the_viewers_rights_filtered_on_the_project"),
    ("the builder lists its projects", M, '"doctype": "Customer",\n   "link_doctype": "PP PQT Project",',
     '"doctype": "Supplier",\n   "link_doctype": "PP PQT Project",', T + "test_the_builder_lists_its_projects"),
    ("store staff never delete a project", M,
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 0,',
     '"role": "Sales User",\n     "read": 1,\n     "write": 1,\n     "create": 1,\n     "delete": 1,',
     T + "test_the_trade_desk_keeps_projects_no_one_but_a_system_manager_deletes"),
    ("whoever sends goods out reads, never changes, a project", M,
     '"role": "Stock User",\n     "read": 1,\n     "write": 0,', '"role": "Stock User",\n     "read": 1,\n     "write": 1,',
     T + "test_the_trade_desk_keeps_projects_no_one_but_a_system_manager_deletes"),
    ("the project opens its help", M, 'recipes/project_quotes.html#projects', 'recipes/project_quotes.html',
     T + "test_the_project_opens_its_help"),
]

def run(name, path, anchor, mutant, test) -> tuple[str, str]:
    tmp = tempfile.mkdtemp(prefix="s60-canary-")
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
