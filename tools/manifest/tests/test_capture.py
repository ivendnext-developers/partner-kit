"""Capture from a site (`capture.py`): only what a person made in Desk, into the manifest's kinds, renamed to the app, and
what the checker refuses left out in its words. The site's answers are recorded below as the site gives them.

    python3 -m unittest discover -s tools/manifest/tests -p test_capture.py
"""

import json
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import capture as C  # noqa: E402
from blank import manifest as blank  # noqa: E402
from validate import validate  # noqa: E402

ME = "consultant@acme.example"
BASE = blank("ACME RULES", "acme_rules")
# the site's answers, as `/api/resource/<type>` and `/api/resource/<type>/<name>` give them (one record each, whole)
SITE = {
    "Custom Field": [
        {"name": "Purchase Order-custom_approval_note", "owner": ME, "dt": "Purchase Order", "fieldname": "custom_approval_note",
         "fieldtype": "Small Text", "label": "Approval note", "insert_after": "supplier", "reqd": 0, "hidden": 0,
         "is_system_generated": 0, "module": None, "idx": 4, "creation": "2026-11-11 09:00:00"},
        {"name": "Purchase Order-custom_needs_approval", "owner": ME, "dt": "Purchase Order", "fieldname": "custom_needs_approval",
         "fieldtype": "Check", "label": "Needs approval", "insert_after": "custom_approval_note", "is_system_generated": 0},
        {"name": "Customer-loyalty_tier", "owner": "Administrator", "dt": "Customer", "fieldname": "loyalty_tier",
         "fieldtype": "Data", "is_system_generated": 0},  # the product's own: made as Administrator
        {"name": "Stock Entry-acme_old_app_field", "owner": ME, "dt": "Stock Entry", "fieldname": "acme_old_app_field",
         "fieldtype": "Data", "is_system_generated": 0},  # an installed app's: its install record names it
    ],
    "Property Setter": [
        {"name": "Purchase Order-custom_approval_note-bold", "owner": ME, "doc_type": "Purchase Order",
         "field_name": "custom_approval_note", "property": "bold", "property_type": "Check", "value": "1",
         "is_system_generated": 0},
    ],
    "Workflow": [
        {"name": "PO over 5000", "owner": ME, "document_type": "Purchase Order", "is_active": 1, "send_email_alert": 0,
         "states": [{"state": "Draft", "doc_status": "0", "allow_edit": "Purchase User", "idx": 1},
                    {"state": "Approved", "doc_status": "1", "allow_edit": "Store Approver", "idx": 2}],
         "transitions": [{"state": "Draft", "action": "Approve", "next_state": "Approved", "allowed": "Store Approver",
                          "condition": "doc.custom_needs_approval == 1", "allow_self_approval": 0}]},
    ],
    "Notification": [
        {"name": "PO waiting", "owner": ME, "is_standard": 0, "document_type": "Purchase Order", "event": "New",
         "channel": "System Notification", "subject": "{{ doc.name }} needs approval",
         "message": "<p>{{ doc.custom_approval_note }}</p>", "recipients": [{"receiver_by_role": "Store Approver"}]},
    ],
    "Print Format": [
        {"name": "PO with note", "owner": ME, "standard": "No", "doc_type": "Purchase Order", "custom_format": 1,
         "print_format_type": "Jinja", "html": "<h2>{{ doc.name }}</h2><p>{{ doc.custom_approval_note }}</p>"},
        {"name": "PO built", "owner": ME, "standard": "No", "doc_type": "Purchase Order", "print_format_builder": 1,
         "format_data": "[]"},
        {"name": "PO with a query", "owner": ME, "standard": "No", "doc_type": "Purchase Order", "custom_format": 1,
         "print_format_type": "Jinja", "html": "{{ frappe.db.sql('select 1') }}"},
    ],
    "Role": [{"name": "Store Approver", "owner": ME, "is_custom": 1}],
    "Custom DocPerm": [
        {"name": "x1", "owner": ME, "parent": "Purchase Order", "role": "Store Approver", "read": 1, "write": 1},
        {"name": "x2", "owner": ME, "parent": "Purchase Order", "role": "Purchase User", "read": 1, "submit": 1},
    ],
    "List View Settings": [{"name": "Purchase Order", "owner": ME, "fields": json.dumps(
        [{"fieldname": "supplier", "label": "Supplier"}, {"fieldname": "custom_needs_approval", "label": "Needs approval"}])}],
    "Report": [
        {"name": "POs waiting", "owner": ME, "is_standard": "No", "report_type": "Report Builder", "ref_doctype": "Purchase Order",
         "json": json.dumps({"columns": [["name", "Purchase Order"], ["custom_needs_approval", "Purchase Order"]],
                             "order_by": "`tabPurchase Order`.`modified` desc"}), "roles": [{"role": "Store Approver"}]},
        {"name": "PO sums", "owner": ME, "is_standard": "No", "report_type": "Query Report", "ref_doctype": "Purchase Order"},
    ],
    "Client Script": [{"name": "PO colour", "owner": ME, "dt": "Purchase Order", "script": "frappe.ui.form.on(...)"}],
}
INSTALLS = [{"name": "acme_old", "status": "installed", "items": json.dumps(
    [{"kind": "custom_field", "name": "Stock Entry-acme_old_app_field"}])}]


class Capture(unittest.TestCase):
    def setUp(self):
        self.r = C.capture(SITE, INSTALLS, BASE, "acme-test.example.com")

    def test_only_what_a_person_made_is_taken(self):
        names = {it["name"] for it in self.r["items"]}
        self.assertNotIn("Customer-loyalty_tier", names)       # made as Administrator: the product's
        self.assertNotIn("Stock Entry-acme_old_app_field", names)  # an installed app's, by its install record
        self.assertIn("Purchase Order-custom_approval_note", names)

    def test_each_field_made_in_desk_takes_the_apps_prefix_wherever_it_is_named(self):  # ⭐
        e = self.r["entries"]
        self.assertEqual([c["fieldname"] for c in e["custom_fields"]], ["acme_rules_approval_note", "acme_rules_needs_approval"])
        self.assertEqual(e["custom_fields"][1]["insert_after"], "acme_rules_approval_note")
        self.assertEqual(e["workflows"][0]["transitions"][0]["condition"], "doc.acme_rules_needs_approval == 1")
        self.assertIn("doc.acme_rules_approval_note", e["notifications"][0]["message"])
        self.assertIn("doc.acme_rules_approval_note", e["print_formats"][0]["html"])
        self.assertEqual(e["property_setters"][0]["field_name"], "acme_rules_approval_note")
        self.assertEqual(e["list_settings"][0]["fields"], ["supplier", "acme_rules_needs_approval"])
        self.assertEqual(e["reports"][0]["columns"], ["name", "acme_rules_needs_approval"])
        self.assertIn("Purchase Order: custom_approval_note is acme_rules_approval_note", self.r["renamed"])

    def test_a_role_made_in_desk_takes_the_prefix_everywhere(self):
        e = self.r["entries"]
        self.assertEqual(e["role_rights"], [{"doctype": "Purchase Order", "role": "ACME RULES Store Approver",
                                             "rights": ["read", "write"], "_from": ("Role", "Store Approver")}])
        self.assertEqual(e["workflows"][0]["states"][1]["allow_edit"], "ACME RULES Store Approver")
        self.assertEqual(e["workflows"][0]["states"][0]["allow_edit"], "Purchase User")  # the customer's own role stays
        self.assertEqual(e["notifications"][0]["recipients"], [{"receiver_by_role": "ACME RULES Store Approver"}])
        self.assertEqual(e["reports"][0]["roles"], ["ACME RULES Store Approver"])

    def test_what_cannot_be_carried_is_left_out_in_the_checkers_words(self):  # ⭐
        left = {(x["type"], x["name"]): x["reason"] for x in self.r["left_out"]}
        self.assertEqual(left[("Client Script", "PO colour")], C.REFUSED_KINDS["client_scripts"])
        self.assertIn("runs code on the site", left[("Report", "PO sums")])
        self.assertEqual(left[("Print Format", "PO built")], C.WORDS["builder_print"])
        self.assertIn("Role Permissions Manager", left[("Custom DocPerm", "Purchase Order: Purchase User")])
        self.assertIn(("Print Format", "PO with a query"), left)  # the checker's own refusal, in its words
        refused = [b["reason"] for b in validate(dict(BASE, print_formats=[{"name": "q", "doc_type": "Purchase Order",
                                                                              "html": "{{ frappe.db.sql('select 1') }}"}]))]
        self.assertIn(left[("Print Format", "PO with a query")], refused)

    def test_what_is_written_passes_the_checker_and_an_untick_leaves_it_out(self):
        m, ids = C.write(BASE, self.r, skip=["Notification/PO waiting"])
        self.assertEqual(validate(m), [])
        self.assertNotIn("notifications", m)
        self.assertIn("Workflow/PO over 5000", ids)
        self.assertNotIn("_from", json.dumps(m))
        only, _ = C.write(BASE, self.r, only=["workflows"])
        self.assertEqual([k for k in only if isinstance(only[k], list) and only[k]], ["workflows"])

    def test_capturing_again_replaces_what_it_wrote_before(self):
        m, _ = C.write(BASE, self.r)
        again, _ = C.write(m, self.r)
        self.assertEqual(len(again["custom_fields"]), 2)
        self.assertEqual(len(again["property_setters"]), 1)

    def test_a_site_with_nothing_made_in_desk_says_so(self):
        r = C.capture({"Custom Field": [SITE["Custom Field"][2]]}, [], BASE, "x.example")
        self.assertEqual(C.lines(r, "x.example"), [C.WORDS["nothing"].format(site="x.example")])

    def test_the_lines_group_by_record_type(self):
        out = C.lines(self.r, "acme-test.example.com")
        self.assertIn("Workflow: PO over 5000", out)
        self.assertTrue(any(x.startswith("Left out: Client Script PO colour:") for x in out))


if __name__ == "__main__":
    unittest.main()
