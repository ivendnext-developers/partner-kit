# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_rolefields.py,
# at development b453a68eac6cc7e039f28a94f6f37147f151ec38; changed: the import, the row and lane ids in the docstring, and one print format that reads through the framework's name (now through the helper's own name: the field is refused either way).
# A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""A field the manifest adds may name the roles that read it (``read_roles``) and
the roles that change it (``write_roles``). Stdlib only. The installer's half (the level, the rows,
the uninstall, an update) is ``test_manifest_role_fields.py``; the till's is ``test_pb9_role_fields.py``."""

import copy
import unittest

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

BASE = {
    "manifest_version": 2,
    "app": "pp_prf",
    "prefix": "PP PRF",
    "version": "0.1.0",
    "custom_fields": [
        {
            "dt": "Customer",
            "fieldname": "pp_prf_licence",
            "fieldtype": "Data",
            "label": "Licence",
            "insert_after": "customer_name",
            "read_roles": ["PP PRF Pharmacist"],
            "write_roles": ["PP PRF Pharmacist"],
        },
        {
            "dt": "Customer",
            "fieldname": "pp_prf_barred",
            "fieldtype": "Check",
            "label": "Barred",
            "insert_after": "customer_name",
            "write_roles": ["PP PRF Claims"],
        },
    ],
}


def refusals(**change):
    m = copy.deepcopy(BASE)
    m["custom_fields"][0].update(change)
    for k, v in change.items():
        if v is None:
            m["custom_fields"][0].pop(k)
    return validate(m)


def reasons(r):
    return " | ".join(x["reason"] for x in r)


class RoleFields(unittest.TestCase):
    def test_read_roles_and_write_roles_are_accepted(self):
        self.assertEqual(validate(copy.deepcopy(BASE)), [])

    def test_read_roles_alone_is_refused_write_roles_is_always_named(self):
        r = refusals(write_roles=None)
        self.assertEqual(len(r), 1, r)
        self.assertIn("write_roles", r[0]["reason"])

    def test_a_roles_key_must_be_a_list_of_names(self):
        for bad in (
            "PP PRF Pharmacist",
            [],
            [""],
            [3],
            ["PP PRF Pharmacist", "PP PRF Pharmacist"],
        ):
            r = refusals(read_roles=bad)
            self.assertEqual(len(r), 1, (bad, r))
            self.assertIn("read_roles", r[0]["reason"])

    def test_a_role_the_framework_hands_out_by_itself_is_refused(self):
        for role in ("Guest", "All", "Desk User", "Administrator", "Pharmacist é"):
            r = refusals(read_roles=[role])
            self.assertEqual(len(r), 1, (role, r))

    def test_a_limited_field_cannot_be_mandatory(self):
        r = refusals(reqd=1)
        self.assertTrue(any("only some roles may change" in x["reason"] for x in r), r)
        r = refusals(mandatory_depends_on="eval:doc.customer_name")
        self.assertEqual(len(r), 1, r)
        self.assertIn("only some roles may change", r[0]["reason"])

    def test_a_layout_or_table_field_cannot_be_limited(self):
        r = refusals(fieldtype="Section Break")
        self.assertIn("holds no value", reasons(r))

    def test_a_manifest_template_naming_a_limited_field_is_refused(self):
        m = copy.deepcopy(BASE)
        m["print_formats"] = [
            {
                "name": "PP PRF Card",
                "doc_type": "Customer",
                "html": "<p>{{ doc.pp_prf_licence }}</p>",
            }
        ]
        m["notifications"] = [
            {
                "name": "PP PRF Note",
                "document_type": "Customer",
                "event": "Save",
                "channel": "System Notification",
                "subject": "Changed",
                "message": "Licence {{ doc.pp_prf_licence }}",
                "recipients": [{"receiver_by_role": "PP PRF Claims"}],
            }
        ]
        r = [x for x in validate(m) if "pp_prf_licence" in x["reason"]]
        self.assertEqual(len(r), 2, validate(m))
        self.assertIn("only some roles read", r[0]["reason"])

    def test_a_template_naming_a_write_limited_field_stays_allowed(self):
        m = copy.deepcopy(BASE)
        m["print_formats"] = [
            {
                "name": "PP PRF Card",
                "doc_type": "Customer",
                "html": "<p>{{ doc.pp_prf_barred }}</p>",
            }
        ]
        self.assertFalse([x for x in validate(m) if "pp_prf_barred" in x["reason"]], validate(m))

    def test_a_fetch_copying_a_field_only_some_roles_read_is_refused(self):
        m = copy.deepcopy(BASE)
        m["custom_fields"].append(
            {
                "dt": "POS Invoice",
                "fieldname": "pp_prf_sale_licence",
                "fieldtype": "Data",
                "label": "Licence",
                "insert_after": "customer",
                "fetch_from": "customer.pp_prf_licence",
            }
        )
        r = [x for x in validate(m) if "fetch_from" in x["reason"]]
        self.assertEqual(len(r), 1, validate(m))

    def test_a_card_chart_report_or_template_on_any_record_naming_it_is_refused(self):
        element = {
            "number_cards": {
                "name": "PP PRF Licensed",
                "document_type": "Customer",
                "function": "Count",
                "filters_json": '[["Customer","pp_prf_licence","is","set"]]',
            },
            "dashboard_charts": {
                "name": "PP PRF Licences",
                "document_type": "Customer",
                "chart_type": "Group By",
                "group_by_based_on": "pp_prf_licence",
            },
            "reports": {
                "name": "PP PRF Patients",
                "ref_doctype": "Customer",
                "report_type": "Report Builder",
                "columns": [["name", "Customer"], ["pp_prf_licence", "Customer"]],
            },
            "print_formats": {
                "name": "PP PRF Sale",
                "doc_type": "POS Invoice",
                "html": "{{ db.get_value('Customer', doc.customer, 'pp_prf_licence') }}",
            },
        }
        for kind, x in element.items():
            m = copy.deepcopy(BASE)
            m[kind] = [x]
            r = [y for y in validate(m) if "pp_prf_licence" in y["reason"]]
            self.assertTrue(r and r[0]["where"] == f"{kind}[0]", (kind, validate(m)))


if __name__ == "__main__":
    unittest.main()
