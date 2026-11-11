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
        self.assertNotIn("Not read by Capture yet", "\n".join(out))  # every kind a person makes in Desk is read (J3b)


# ── J3b: the retail kinds, as the POS install writes them and Desk saves them (`manifest_install.py`, each record's own form)
RETAIL = {
    "Custom Field": [
        {"name": "Customer-custom_id_number", "owner": ME, "dt": "Customer", "fieldname": "custom_id_number",
         "fieldtype": "Data", "label": "ID number", "insert_after": "customer_name", "is_system_generated": 0},
        {"name": "Item-custom_shelf_note", "owner": ME, "dt": "Item", "fieldname": "custom_shelf_note", "fieldtype": "Data",
         "label": "Shelf note", "insert_after": "item_name", "is_system_generated": 0},
    ],
    "Retail Label Layout": [
        {"name": "Shelf 50x25", "owner": ME, "label_name": "Shelf 50x25", "kind": "html", "enabled": 1, "width_mm": 50.0,
         "height_mm": 25.0, "per_row": 2, "template": "<div>{item_name}</div>{barcode_svg}<div>{item.custom_shelf_note}</div>"},
        {"name": "Old label", "owner": ME, "label_name": "Old label", "kind": "html", "enabled": 0, "width_mm": 40.0,
         "height_mm": 20.0, "per_row": 1, "template": "<div>{item_name}</div>"},
    ],
    "Retail List Mark": [
        {"name": "a1b2c3d4e5", "owner": ME, "record_type": "Item", "label": "Not stocked", "colour": "orange", "enabled": 1,
         "sequence": 0, "conditions": [{"name": "r1", "field": "is_stock_item", "operator": "=", "value": "0", "idx": 1},
                                        {"name": "r2", "field": "custom_shelf_note", "operator": "is set", "value": None}]},
    ],
    "Transaction Item Attribute": [
        {"name": "IMEI", "owner": ME, "attribute_name": "IMEI", "validation_type": "No Validation", "regex_pattern": None,
         "sequence": 0, "default_value": None, "active": 1}],
    "Retail Scan Source": [
        {"name": "Coupon books", "owner": ME, "source_name": "Coupon books", "record_type": "Serial No",
         "barcode_field": "serial_no", "enabled": 1, "sequence": 0, "item_from": "item_code", "status_field": "status",
         "available_values": "Active\nDelivered\n", "capture_as": "IMEI", "batch_from": "", "warehouse_field": None},
    ],
    "Retail Register Book": [
        {"name": "acme_liquor.stock_book", "owner": ME, "book": "acme_liquor.stock_book", "title": "Liquor stock book",
         "data_set": "acme_liquor", "cite": "Excise rules, part 4", "enabled": 0, "certified": 0, "medium": "printed_book",
         "source_app": None, "numbering": "book_store_item", "balance": 1, "correction": "reversing_line",
         "retention_years": 5, "count_role": "Stock Manager", "item_scope": json.dumps({"item_groups": ["Beer"]}),
         "conditions": json.dumps([{"field": "direction", "operator": "=", "value": "Out"}]), "required": "[]",
         "columns": json.dumps([{"label": "Date", "value": ["movement_date"]}, {"label": "Quantity", "value": ["qty", "uom"]}]),
         "details": "{}", "authority": None, "columns_from": "", "register_stores": json.dumps({"Main - AC": "Main"})},
        {"name": "xx_rx.npp", "owner": ME, "book": "xx_rx.npp", "title": "An app's", "data_set": "xx_rx", "cite": "x",
         "enabled": 0, "source_app": "xx_rx_app", "numbering": "book_store", "correction": "dated_note",
         "retention_years": 2, "count_role": "Stock Manager", "item_scope": "{}", "columns": "[]"},  # kept from an uninstall
    ],
    "Retail Save Rule": [
        {"name": "Discount over 0 needs a reason", "owner": ME, "rule_name": "Discount over 0 needs a reason",
         "record_type": "Sales Order", "kind": "threshold", "field": "discount_amount", "operator": ">", "value": "0",
         "mode": "refuse", "enabled": 1, "factor": 1.0, "offset": 0.0, "decimals": 0, "judge_on_change": 0,
         "bypass_roles": "Sales Manager\nAccounts Manager", "message": "Give a reason for the discount.",
         "conditions": [{"name": "c1", "field": "order_type", "operator": "=", "value": "Sales"}]},
        {"name": "Off rule", "owner": ME, "rule_name": "Off rule", "record_type": "Sales Order", "kind": "required_when",
         "enabled": 0, "conditions": []},
    ],
    "Sale Attribute": [
        {"name": "Gift message", "owner": ME, "attribute_name": "Gift message", "validation_type": "No Validation",
         "doctype_name": None, "regex_pattern": None, "sequence": 905, "default_value": None, "required": 0, "active": 1},
        {"name": "Sales person", "owner": ME, "attribute_name": "Sales person", "validation_type": "DocType",
         "doctype_name": "Sales Person", "sequence": 906, "required": 0, "active": 1},
        {"name": "Must ask", "owner": ME, "attribute_name": "Must ask", "validation_type": "No Validation", "sequence": 907,
         "required": 1, "active": 1},
        {"name": "Loyalty card no", "owner": ME, "attribute_name": "Loyalty card no", "validation_type": "No Validation",
         "regex_pattern": "^[0-9]{10}$", "sequence": 908, "required": 0, "active": 1},
        {"name": "IVENDNEXT AGE ID Checked", "owner": "Administrator", "attribute_name": "IVENDNEXT AGE ID Checked",
         "sequence": 900, "required": 0, "active": 1},
    ],
    # a row added to a theme the product made takes the theme's owner (the framework's set_user_and_timestamp)
    "Retail POS Theme Field": [
        {"name": "f1row", "owner": "Administrator", "parent": "Ironwood", "parenttype": "Retail POS Theme",
         "parentfield": "field_rules", "surface": "customer_create", "field": "custom_id_number", "action": "show",
         "label": None, "language": None, "sequence": 1},
        {"name": "f2row", "owner": "Administrator", "parent": "Ironwood", "parenttype": "Retail POS Theme",
         "parentfield": "field_rules", "surface": "cart_line", "field": "item_name", "action": "relabel", "label": "Product"},
        {"name": "f3row", "owner": "Administrator", "parent": "Ironwood", "parenttype": "Retail POS Theme",
         "parentfield": "field_rules", "surface": "cart_line", "field": "item_name", "action": "relabel", "label": "Producto",
         "language": "es"},
        {"name": "appsrow", "owner": "Administrator", "parent": "Ironwood", "parenttype": "Retail POS Theme",
         "parentfield": "field_rules", "surface": "customer_card", "field": "loyalty_points", "action": "hide"},
    ],
    # Customize Form's own rows: parenttype Customize Form, custom 1 (customize_form.set_property_setters_for_actions_and_links)
    "DocType Link": [
        {"name": "lk1", "owner": ME, "parent": "Customer", "parenttype": "Customize Form", "parentfield": "links",
         "link_doctype": "Sales Order", "link_fieldname": "customer", "group": "Orders", "custom": 1, "hidden": 0,
         "is_child_table": 0, "parent_doctype": None, "table_fieldname": None},
        {"name": "lk2", "owner": ME, "parent": "Item", "parenttype": "Customize Form", "parentfield": "links",
         "link_doctype": "Sales Order", "link_fieldname": "item_code", "custom": 1, "is_child_table": 1,
         "parent_doctype": "Sales Order", "table_fieldname": "items"},
    ],
    "DocType State": [{"name": "st1", "owner": ME, "parent": "Sales Order", "title": "Waiting", "color": "Orange", "custom": 1}],
    "Retail POS Theme": [{"name": "Acme Till", "owner": ME, "theme_name": "Acme Till", "layout": "classic"}],  # Save as new
    "Property Setter": [
        {"name": "Customer-lk9-hidden", "owner": ME, "doc_type": "Customer", "field_name": None, "row_name": "lk9",
         "doctype_or_field": "DocType Link", "property": "hidden", "property_type": "Check", "value": "1",
         "is_system_generated": 0},
        {"name": "Customer-main-links_order", "owner": ME, "doc_type": "Customer", "field_name": None,
         "doctype_or_field": "DocType", "property": "links_order", "property_type": "Small Text",
         "value": json.dumps(["lk1", "lk9"]), "is_system_generated": 0},
    ],
}
RETAIL_INSTALLS = [{"name": "acme_loyal", "status": "installed", "items": json.dumps([{"kind": "field_rule", "name": "appsrow"}])}]


class Retail(unittest.TestCase):
    """Row J3b: each retail kind a person makes in Desk is read, mapped back into the recipe's shape, renamed and checked."""

    def setUp(self):
        self.r = C.capture(RETAIL, RETAIL_INSTALLS, BASE, "acme-test.example.com")
        self.e = self.r["entries"]
        self.left = {(x["type"], x["name"]): x["reason"] for x in self.r["left_out"]}

    def test_each_retail_kind_has_its_read(self):
        reads = {x["doctype"]: x for x in C.reads()}
        for dt in ("Retail Label Layout", "Retail List Mark", "Retail Scan Source", "Retail Register Book", "Retail Save Rule",
                   "Sale Attribute", "Retail POS Theme Field", "DocType Link"):
            self.assertIn(dt, C.READ_TYPES)
            self.assertIn(dt, reads)
        self.assertEqual(reads["DocType Link"]["parent"], "Customize Form")
        self.assertEqual(reads["Retail POS Theme Field"]["parent"], "Retail POS Theme")
        self.assertNotIn(C.PERSON_FILTER[1], reads["Retail POS Theme Field"]["filters"])  # a theme row takes its theme's owner
        self.assertIn(C.PERSON_FILTER[1], reads["Retail Label Layout"]["filters"])
        self.assertTrue(reads["Retail List Mark"]["whole"] and reads["Retail Save Rule"]["whole"])  # their conditions

    def test_a_label_layout(self):
        self.assertEqual(self.e["label_layouts"], [{
            "label_name": "Shelf 50x25", "kind": "html", "width_mm": 50.0, "height_mm": 25.0, "per_row": 2,
            "template": "<div>{item_name}</div>{barcode_svg}<div>{item.acme_rules_shelf_note}</div>",
            "_from": ("Retail Label Layout", "Shelf 50x25")}])
        self.assertIn("switched off", self.left[("Retail Label Layout", "Old label")])

    def test_a_list_mark_keeps_a_value_of_0(self):
        self.assertEqual(self.e["list_marks"][0]["conditions"],
                         [{"field": "is_stock_item", "operator": "=", "value": "0"},
                          {"field": "acme_rules_shelf_note", "operator": "is set"}])
        self.assertEqual((self.e["list_marks"][0]["colour"], self.e["list_marks"][0]["sequence"]), ("orange", 0))  # first
        self.assertIn("Retail List Mark/Item: Not stocked", [i["id"] for i in self.r["items"]])  # by its label, not its row id

    def test_a_scan_source(self):
        self.assertEqual(self.e["scan_sources"], [{
            "source_name": "Coupon books", "record_type": "Serial No", "barcode_field": "serial_no", "capture_as": "IMEI",
            "item_from": "item_code", "status_field": "status", "sequence": 0, "available_values": ["Active", "Delivered"],
            "_from": ("Retail Scan Source", "Coupon books")}])
        # the line detail it records into travels as a default record (made at install, before the scan sources)
        self.assertEqual(self.e["records"], [{"doctype": "Transaction Item Attribute", "name": "IMEI", "values": {
            "attribute_name": "IMEI", "validation_type": "No Validation", "sequence": 0, "active": 1},
            "_from": ("Transaction Item Attribute", "IMEI")}])

    def test_a_register_book_without_the_shops_register_stores(self):
        b = self.e["register_books"]
        self.assertEqual(len(b), 1)  # the app's book, kept by an uninstall, names its app: not a person's
        self.assertEqual(b[0]["items"], {"item_groups": ["Beer"]})
        self.assertEqual(b[0]["columns"][1], {"label": "Quantity", "value": ["qty", "uom"]})
        self.assertEqual((b[0]["enabled"], b[0]["certified"]), (0, 0))  # installed as it declares: off stays off
        self.assertNotIn("register_stores", b[0])
        self.assertNotIn("item_scope", b[0])
        self.assertNotIn("details", b[0])  # empty

    def test_a_save_rule_keeps_its_lists_its_conditions_and_a_threshold_of_0(self):
        rule = self.e["save_rules"][0]
        self.assertEqual(rule["value"], "0")
        self.assertEqual(rule["bypass_roles"], ["Sales Manager", "Accounts Manager"])
        self.assertEqual(rule["conditions"], [{"field": "order_type", "operator": "=", "value": "Sales"}])
        self.assertIn("switched off", self.left[("Retail Save Rule", "Off rule")])

    def test_sale_details(self):
        by = {a["name"]: a for a in self.e["sale_attributes"]}
        self.assertEqual(by["Gift message"], {"name": "Gift message", "sequence": 905, "_from": ("Sale Attribute", "Gift message")})
        self.assertEqual((by["Sales person"]["validation_type"], by["Sales person"]["doctype_name"]), ("DocType", "Sales Person"))
        self.assertNotIn("IVENDNEXT AGE ID Checked", by)  # the product's
        self.assertIn("would stop every sale", self.left[("Sale Attribute", "Must ask")])  # the checker's own words
        self.assertEqual(self.left[("Sale Attribute", "Loyalty card no")], C.WORDS["sale_check"])  # never installed unchecked

    def test_till_field_rules_are_the_rows_no_app_made_and_take_the_renamed_field(self):
        self.assertEqual([{k: v for k, v in x.items() if k != "_from"} for x in self.e["field_rules"]], [
            {"theme": "Ironwood", "surface": "customer_create", "field": "acme_rules_id_number", "action": "show", "sequence": 1},
            {"theme": "Ironwood", "surface": "cart_line", "field": "item_name", "action": "relabel", "label": "Product"},
            {"theme": "Ironwood", "surface": "cart_line", "field": "item_name", "action": "relabel", "label": "Producto",
             "language": "es"}])
        self.assertIn("Retail POS Theme Field/Ironwood: relabel item_name on cart_line (es)", [i["id"] for i in self.r["items"]])
        self.assertIn("Retail POS Theme Field/Ironwood: show custom_id_number on customer_create", [i["id"] for i in self.r["items"]])
        self.assertEqual(self.left[("Retail POS Theme", "Acme Till")], C.WORDS["theme"].format(name="Acme Till"))

    def test_a_connections_link_and_what_customize_form_makes_that_no_kind_carries(self):
        self.assertEqual(self.e["links"], [{"doctype": "Customer", "link_doctype": "Sales Order", "link_fieldname": "customer",
                                            "group": "Orders", "_from": ("DocType Link", "Customer: Sales Order (customer)")}])
        self.assertEqual(self.left[("DocType Link", "Item: Sales Order (item_code)")], C.WORDS["child_link"])
        self.assertIn("list mark", self.left[("DocType State", "Sales Order: Waiting")])
        self.assertIn("own Connections links", self.left[("Property Setter", "Customer-lk9-hidden")])  # not a setter on Customer
        self.assertIn("order of Customer's Connections links", self.left[("Property Setter", "Customer-main-links_order")])
        self.assertNotIn("property_setters", self.e)

    def test_everything_written_passes_the_checker(self):  # ⭐
        m, ids = C.write(BASE, self.r)
        self.assertEqual(validate(m), [])
        self.assertEqual({k for k in m if isinstance(m[k], list) and m[k]} >= {
            "label_layouts", "list_marks", "scan_sources", "register_books", "save_rules", "sale_attributes", "field_rules",
            "links", "records"}, True)
        again, _ = C.write(m, self.r)  # a second capture replaces its own, a field rule by what it does
        self.assertEqual(len(again["field_rules"]), 3)  # a relabel in Spanish is a rule of its own


class Parked(unittest.TestCase):
    """Row J3b item (3): what the J3 reviews parked, each met by a consultant capturing a chain's set-up."""

    def test_a_name_the_product_also_uses_on_another_record_type_stays_theirs_there(self):
        site = {"Custom Field": [{"name": "Purchase Order-custom_store", "owner": ME, "dt": "Purchase Order",
                                  "fieldname": "custom_store", "fieldtype": "Data", "is_system_generated": 0}],
                "Print Format": [{"name": "PO store", "owner": ME, "standard": "No", "doc_type": "Purchase Order",
                                  "html": "<p>{{ doc.custom_store }}</p>"}],
                "Report": [{"name": "Sales by store", "owner": ME, "is_standard": "No", "report_type": "Report Builder",
                            "ref_doctype": "POS Invoice", "json": json.dumps({"fields": [["custom_store", "POS Invoice"]]})}]}
        # the site's answer: POS Invoice has the product's own custom_store
        r = C.capture(site, [], BASE, "x", others=[["Purchase Order", "custom_store"], ["POS Invoice", "custom_store"]])
        self.assertEqual(r["entries"]["print_formats"][0]["html"], "<p>{{ doc.acme_rules_store }}</p>")
        self.assertEqual(r["entries"]["reports"][0]["columns"], ["custom_store"])  # the product's field, as it is
        self.assertEqual(C.person_fieldnames(site), ["custom_store"])

    def test_an_unticked_field_keeps_its_name_where_the_kept_entries_name_it(self):  # ⭐
        r = C.capture(SITE, INSTALLS, BASE, "acme-test.example.com")
        m, _ = C.write(BASE, r, skip=["Custom Field/Purchase Order-custom_approval_note"])
        self.assertIn("doc.custom_approval_note", m["print_formats"][0]["html"])  # the customer's site has its own
        self.assertEqual(m["workflows"][0]["transitions"][0]["condition"], "doc.acme_rules_needs_approval == 1")
        self.assertFalse(any("custom_approval_note is" in x for x in r["renamed"]))  # said only for what is written
        m2, _ = C.write(BASE, r, skip=["Role/Store Approver"])
        self.assertEqual(m2["workflows"][0]["states"][1]["allow_edit"], "Store Approver")

    def test_an_untick_on_one_record_type_keeps_the_same_name_written_on_another(self):  # ⭐ reviewer-leaf
        site = {"Custom Field": [{"name": f"{dt}-custom_store", "owner": ME, "dt": dt, "fieldname": "custom_store",
                                  "fieldtype": "Data", "is_system_generated": 0} for dt in ("Purchase Order", "Sales Order")],
                "Print Format": [{"name": f"{dt} store", "owner": ME, "standard": "No", "doc_type": dt,
                                  "html": "<p>{{ doc.custom_store }}</p>"} for dt in ("Purchase Order", "Sales Order")]}
        r = C.capture(site, [], BASE, "x")
        m, ids = C.write(BASE, r, skip=["Custom Field/Sales Order-custom_store"])
        self.assertEqual(validate(m), [])
        self.assertEqual([(c["dt"], c["fieldname"]) for c in m["custom_fields"]], [("Purchase Order", "acme_rules_store")])
        html = {pf["doc_type"]: pf["html"] for pf in m["print_formats"]}
        self.assertEqual(html, {"Purchase Order": "<p>{{ doc.acme_rules_store }}</p>",
                                "Sales Order": "<p>{{ doc.custom_store }}</p>"})  # the customer's own field there

    def test_an_untick_of_a_field_a_kept_entry_writes_leaves_that_entry_out_in_the_checkers_words(self):
        site = {"Custom Field": [{"name": "Purchase Order-custom_told", "owner": ME, "dt": "Purchase Order",
                                  "fieldname": "custom_told", "fieldtype": "Check", "is_system_generated": 0}],
                "Notification": [{"name": "PO told", "owner": ME, "is_standard": 0, "enabled": 1,
                                  "document_type": "Purchase Order", "event": "New", "channel": "System Notification",
                                  "subject": "x", "set_property_after_alert": "custom_told", "property_value": "1",
                                  "recipients": [{"receiver_by_role": "Purchase User"}]}]}
        r = C.capture(site, [], BASE, "x")
        m, ids = C.write(BASE, r, skip=["Custom Field/Purchase Order-custom_told"])
        self.assertEqual((ids, validate(m)), ([], []))
        self.assertIn("set_property_after_alert", {x["name"]: x["reason"] for x in r["left_out"]}["PO told"])

    def test_capturing_again_after_a_record_moved_replaces_it(self):  # ⭐ the walk: a scan source moved to another table
        def site(table):
            return {"Retail Scan Source": [{"name": "Price tags", "owner": ME, "source_name": "Price tags", "enabled": 1,
                                            "record_type": table, "barcode_field": "name", "item_from": "item_code"}],
                    "Print Format": [{"name": "Tag", "owner": ME, "standard": "No", "doc_type": table, "html": "<p>x</p>"}]}
        m, _ = C.write(BASE, C.capture(site("Serial No"), [], BASE, "x"))
        again, _ = C.write(m, C.capture(site("Item Price"), [], m, "x"))
        self.assertEqual([x["record_type"] for x in again["scan_sources"]], ["Item Price"])
        self.assertEqual([x["doc_type"] for x in again["print_formats"]], ["Item Price"])

    def test_a_type_the_key_may_not_read_is_named_with_the_role_that_may(self):  # J6 F17
        r = C.capture(SITE, INSTALLS, BASE, "acme-test.example.com", unread=["Server Script", "Retail Scan Source"])
        left = {x["type"]: x["reason"] for x in r["left_out"] if x["name"] == "(all)"}
        self.assertIn("Script Manager may", left["Server Script"])
        self.assertIn("nothing is lost", left["Server Script"])
        self.assertIn("capture again", left["Retail Scan Source"])
        self.assertTrue(r["items"])  # the rest is read and captured

    def test_a_long_name_is_shortened_to_64(self):
        long = "custom_" + "a" * 57  # 64, as Desk allows
        r = C.capture({"Custom Field": [{"name": f"Item-{long}", "owner": ME, "dt": "Item", "fieldname": long,
                                         "fieldtype": "Data", "is_system_generated": 0}]}, [],
                      blank("ACME RULES LONG", "acme_rules_long"), "x")
        fn = r["entries"]["custom_fields"][0]["fieldname"]
        self.assertEqual(len(fn), C.FIELD_MAX)
        self.assertTrue(fn.startswith("acme_rules_long_"))
        self.assertIn("shortened to 64 characters", r["renamed"][0])
        self.assertEqual(C._short("a" * 70, {"a" * 64}), "a" * 62 + "_2")

    def test_a_notification_sets_its_field_and_a_workflow_overrides_the_status(self):
        site = {"Custom Field": [{"name": "Purchase Order-custom_told", "owner": ME, "dt": "Purchase Order",
                                  "fieldname": "custom_told", "fieldtype": "Check", "is_system_generated": 0}],
                "Notification": [{"name": "PO told", "owner": ME, "is_standard": 0, "enabled": 1,
                                  "document_type": "Purchase Order", "event": "New", "channel": "System Notification",
                                  "subject": "x", "set_property_after_alert": "custom_told", "property_value": "1",
                                  "recipients": [{"receiver_by_role": "Purchase User"}]}],
                "Workflow": [{"name": "PO flow", "owner": ME, "document_type": "Purchase Order", "is_active": 1,
                              "override_status": 1, "states": [{"state": "Draft", "doc_status": "0", "allow_edit": "Purchase User"},
                                                                {"state": "Done", "doc_status": "0", "allow_edit": "Purchase User"}],
                              "transitions": [{"state": "Draft", "action": "Finish", "next_state": "Done",
                                               "allowed": "Purchase User"}]}]}
        r = C.capture(site, [], BASE, "x")
        n = r["entries"]["notifications"][0]
        self.assertEqual((n["set_property_after_alert"], n["property_value"]), ("acme_rules_told", "1"))
        self.assertEqual(r["entries"]["workflows"][0]["override_status"], 1)
        self.assertEqual(r["left_out"], [])


if __name__ == "__main__":
    unittest.main()
