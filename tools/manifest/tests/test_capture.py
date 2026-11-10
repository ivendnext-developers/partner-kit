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
        {"name": "Purchase Order-workflow_state", "owner": ME, "dt": "Purchase Order", "fieldname": "workflow_state",
         "fieldtype": "Link", "options": "Workflow State", "hidden": 1, "is_system_generated": 0},  # Desk's, for the workflow
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
        {"name": "Purchase Order-main-field_order", "owner": ME, "doc_type": "Purchase Order", "field_name": "",
         "property": "field_order", "property_type": "Data", "value": "[\"supplier\"]", "is_system_generated": 0},
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
        {"name": "PO draft flow", "owner": ME, "document_type": "Purchase Order", "is_active": 0, "states": [], "transitions": []},
    ],
    "Notification": [
        {"name": "PO waiting", "owner": ME, "is_standard": 0, "enabled": 1, "document_type": "Purchase Order", "event": "New",
         "channel": "System Notification", "subject": "{{ doc.name }} needs approval",
         "message": "<p>{{ doc.custom_approval_note }}</p>", "recipients": [{"receiver_by_role": "Store Approver"}]},
        {"name": "PO old alert", "owner": ME, "is_standard": 0, "enabled": 0, "document_type": "Purchase Order", "event": "New",
         "channel": "System Notification", "subject": "x", "recipients": []},
    ],
    "Print Format": [
        {"name": "PO with note", "owner": ME, "standard": "No", "module": "Buying", "doc_type": "Purchase Order", "custom_format": 1,
         "print_format_type": "Jinja", "html": "<h2>{{ doc.name }}</h2><p>{{ doc.custom_approval_note }}</p>"},
        {"name": "PO built", "owner": ME, "standard": "No", "module": "Buying", "doc_type": "Purchase Order",
         "print_format_builder_beta": 1, "format_data": "[]"},
        {"name": "PO with a script", "owner": ME, "standard": "No", "doc_type": "Purchase Order", "custom_format": 1,
         "print_format_type": "Jinja", "html": "<p>{{ doc.name }}</p><script>alert(1)</script>"},
    ],
    "Role": [{"name": "Store Approver", "owner": ME, "is_custom": 0}],  # Desk leaves is_custom at 0
    "Custom DocPerm": [
        {"name": "x1", "owner": ME, "parent": "Purchase Order", "role": "Store Approver", "read": 1, "write": 1, "submit": 1,
         "permlevel": 0},
        {"name": "x3", "owner": ME, "parent": "Purchase Order", "role": "Store Approver", "write": 1, "permlevel": 1},
        {"name": "x2", "owner": ME, "parent": "Purchase Order", "role": "Purchase User", "read": 1, "submit": 1},
    ],
    "List View Settings": [{"name": "Purchase Order", "owner": ME, "fields": json.dumps(
        [{"fieldname": "supplier", "label": "Supplier"}, {"fieldname": "custom_needs_approval", "label": "Needs approval"}])}],
    "Report": [
        {"name": "POs waiting", "owner": ME, "is_standard": "No", "module": "Buying", "report_type": "Report Builder",
         "ref_doctype": "Purchase Order", "json": json.dumps({  # as Report View saves it
             "fields": [["name", "Purchase Order"], ["custom_needs_approval", "Purchase Order"]],
             "filters": [["Purchase Order", "status", "=", "Draft", False]],
             "order_by": "`tabPurchase Order`.`modified` desc"}), "roles": [{"role": "Store Approver"}]},
        {"name": "PO sums", "owner": ME, "is_standard": "No", "report_type": "Query Report", "ref_doctype": "Purchase Order"},
    ],
    "Number Card": [{"name": "POs to approve", "owner": ME, "is_standard": 0, "document_type": "Purchase Order",
                     "function": "Count", "filters_json": json.dumps([["Purchase Order", "status", "=", "Draft", False]])}],
    "Workspace": [{"name": "Buying desk", "owner": ME, "public": 1, "content": json.dumps(
        [{"id": "a1", "type": "shortcut", "data": {"shortcut_name": "Purchase Order", "col": 4}}]),
        "shortcuts": [{"type": "DocType", "link_to": "Purchase Order", "label": "Purchase Order"}]}],
    "Translation": [{"name": "t1", "owner": ME, "language": "fr", "source_text": "Gift note", "translated_text": "Mot cadeau"},
                    {"name": "t2", "owner": ME, "language": "fr", "source_text": "Old app", "translated_text": "Vieille"}],
    "Client Script": [{"name": "PO colour", "owner": ME, "dt": "Purchase Order", "script": "// colours the form"}],
}
INSTALLS = [{"name": "acme_old", "status": "installed", "items": json.dumps(
    [{"kind": "custom_field", "name": "Stock Entry-acme_old_app_field"}, {"kind": "translation", "language": "fr",
                                                                           "rows": ["t2"]}])}]


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
        self.assertEqual(e["reports"][0]["filters"], [["status", "=", "Draft"]])
        self.assertEqual(e["reports"][0]["order_by"], "modified desc")
        self.assertIn("Purchase Order: custom_approval_note is acme_rules_approval_note", self.r["renamed"])

    def test_a_role_made_in_desk_takes_the_prefix_everywhere(self):
        e = self.r["entries"]
        self.assertEqual(e["role_rights"], [{"doctype": "Purchase Order", "role": "ACME RULES Store Approver",
                                             "rights": ["read", "write", "submit"], "_from": ("Role", "Store Approver")}])
        left = {(x["type"], x["name"]): x["reason"] for x in self.r["left_out"]}
        self.assertIn("level 1", left[("Custom DocPerm", "Purchase Order: Store Approver")])
        self.assertEqual(e["workflows"][0]["states"][1]["allow_edit"], "ACME RULES Store Approver")
        self.assertEqual(e["workflows"][0]["states"][0]["allow_edit"], "Purchase User")  # the customer's own role stays
        self.assertEqual(e["notifications"][0]["recipients"], [{"receiver_by_role": "ACME RULES Store Approver"}])
        self.assertEqual(e["reports"][0]["roles"], ["ACME RULES Store Approver"])

    def test_a_two_person_step_stays_two_person_and_what_is_off_is_left_out(self):
        self.assertEqual(self.r["entries"]["workflows"][0]["transitions"][0]["allow_self_approval"], 0)
        left = {(x["type"], x["name"]): x["reason"] for x in self.r["left_out"]}
        self.assertIn("switched off", left[("Workflow", "PO draft flow")])
        self.assertIn("switched off", left[("Notification", "PO old alert")])
        self.assertEqual(left[("Property Setter", "Purchase Order-main-field_order")], C.WORDS["field_order"])

    def test_the_workflow_state_field_desk_makes_is_never_taken_nor_renamed(self):
        e = self.r["entries"]
        self.assertNotIn("workflow_state", [c["fieldname"] for c in e["custom_fields"]])
        self.assertNotIn("acme_rules_workflow_state", json.dumps(e))

    def test_a_card_keeps_its_filters_a_workspace_its_shortcut_and_an_apps_translations_stay_its(self):
        e = self.r["entries"]
        self.assertEqual(e["number_cards"][0]["filters"], [["status", "=", "Draft"]])
        self.assertNotIn("filters_json", json.dumps(e["number_cards"]))
        self.assertEqual(e["workspaces"][0]["blocks"], [{"type": "shortcut", "data": {"shortcut_name": "Purchase Order", "col": 4}}])
        self.assertEqual(e["translations"], [{"language": "fr", "words": {"Gift note": "Mot cadeau"},
                                              "_from": ("Translation", "fr")}])

    def test_desk_sets_a_module_on_a_persons_print_format_and_report_and_they_are_still_taken(self):
        self.assertIn("Print Format/PO with note", [i["id"] for i in self.r["items"]])
        self.assertIn("Report/POs waiting", [i["id"] for i in self.r["items"]])

    def test_a_second_capture_replaces_its_own_entries_and_leaves_none_out(self):
        m, _ = C.write(BASE, self.r)
        again = C.capture(SITE, INSTALLS, m, "acme-test.example.com")
        self.assertEqual(sorted(x["name"] for x in again["left_out"]), sorted(x["name"] for x in self.r["left_out"]))

    def test_what_cannot_be_carried_is_left_out_in_the_checkers_words(self):  # ⭐
        left = {(x["type"], x["name"]): x["reason"] for x in self.r["left_out"]}
        self.assertEqual(left[("Client Script", "PO colour")], C.REFUSED_KINDS["client_scripts"])
        self.assertIn("runs code on the site", left[("Report", "PO sums")])
        self.assertEqual(left[("Print Format", "PO built")], C.WORDS["builder_print"])
        self.assertEqual(left[("Custom DocPerm", "Purchase Order")], C.WORDS["their_role"].format(roles="Purchase User"))
        self.assertIn(("Print Format", "PO with a script"), left)  # the checker's own refusal, in its words
        refused = [b["reason"] for b in validate(dict(BASE, print_formats=[{"name": "q", "doc_type": "Purchase Order",
                                                                              "html": "<p>{{ doc.name }}</p><script>alert(1)</script>"}]))]
        self.assertIn(left[("Print Format", "PO with a script")], refused)

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
        r = C.capture({"Custom Field": [c for c in SITE["Custom Field"] if c["owner"] == "Administrator"]}, [], BASE, "x.example")
        self.assertEqual(C.lines(r, "x.example"), [C.WORDS["nothing"].format(site="x.example")])

    def test_the_lines_group_by_record_type(self):
        out = C.lines(self.r, "acme-test.example.com")
        self.assertIn("Workflow: PO over 5000", out)
        self.assertTrue(any(x.startswith("Left out: Client Script PO colour:") for x in out))


if __name__ == "__main__":
    unittest.main()
