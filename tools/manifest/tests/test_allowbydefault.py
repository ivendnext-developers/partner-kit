# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_allowbydefault.py,
# at development cff85a09aa4d9391bd0de4af68964d2181a753a5; changed: the import, one line so unittest runs it, and the docstring's ids. A defect here is a defect there:
# report it with the Kit defect form (feedback/README.md).
"""A partner's app may do what the customer's administrator can do in Desk. The checker refuses only a wrong money, tax, stock or fiscal
figure, the till's own sale or customer failing to save, customer data sent where the customer
did not see, or someone acting as someone else. Stdlib only, no bench; ``ABD`` is installed as
written by the product's own install test."""

import copy
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from validate import validate  # noqa: E402

WORKFLOW = {
    "name": "PO Approval",
    "document_type": "Purchase Order",
    "send_email_alert": 1,
    "states": [
        {"state": "Draft", "doc_status": 0, "allow_edit": "Purchase User"},
        {"state": "Approved", "doc_status": 1, "allow_edit": "PO Approver"},
        {"state": "Rejected", "doc_status": 0, "allow_edit": "PO Approver"},
        {"state": "Cancelled", "doc_status": 2, "allow_edit": "PO Approver"},
    ],
    "transitions": [
        {
            "state": "Draft",
            "action": "Approve",
            "next_state": "Approved",
            "allowed": "PO Approver",
            "condition": "doc.grand_total > 50000",
        },
        {"state": "Draft", "action": "Reject", "next_state": "Rejected", "allowed": "PO Approver"},
        {
            "state": "Approved",
            "action": "Cancel",
            "next_state": "Cancelled",
            "allowed": "PO Approver",
        },
    ],
}
ABD = {
    "manifest_version": 2,
    "app": "pp_abd",
    "prefix": "PP ABD",
    "title": "Purchase approvals",
    "version": "0.1.0",
    "custom_fields": [
        {
            "dt": "Purchase Order",
            "fieldname": "pp_abd_budget_code",
            "fieldtype": "Data",
            "label": "Budget code",
            "reqd": 1,
            "insert_after": "supplier",
        }
    ],
    "property_setters": [
        {
            "doc_type": "Purchase Order",
            "field_name": "schedule_date",
            "property": "label",
            "value": "Needed by",
        }
    ],
    "workflows": [WORKFLOW],
    "notifications": [
        {
            "name": "PO submitted",
            "document_type": "Purchase Order",
            "event": "Submit",
            "channel": "Email",
            "subject": "Purchase Order {{ doc.name }} is submitted",
            "message": "{{ doc.supplier }}: {{ doc.grand_total }}",
            "recipients": [{"receiver_by_document_field": "owner"}],
            "attach_print": 1,
        }
    ],
    "naming_rules": [
        {"document_type": "Material Request", "prefix": "MR-BLR-", "prefix_digits": 5}
    ],
    "list_settings": [
        {"doctype": "Purchase Order", "fields": ["supplier", "grand_total", "pp_abd_budget_code"]}
    ],
}


def test_a_back_office_app_checks_as_written():
    assert validate(ABD) == []


def test_the_tills_sale_and_customer_are_refused_one_line_each():
    m = copy.deepcopy(ABD)
    m["workflows"] = [dict(WORKFLOW, name="Sale approval", document_type="POS Invoice")]
    m["custom_fields"] = [dict(ABD["custom_fields"][0], dt="Customer")]
    del m["notifications"], m["list_settings"], m["property_setters"]
    out = validate(m)
    assert [(r["where"], r["name"]) for r in out] == [
        ("custom_fields[0]", "pp_abd_budget_code"),
        ("workflows[0]", "Sale approval"),
    ], out
    for r in out:
        assert "\n" not in r["reason"] and "the till" in r["reason"], r


def load_tests(loader, tests, pattern):
    return unittest.TestSuite(unittest.FunctionTestCase(f) for n, f in sorted(globals().items()) if n.startswith("test_"))
