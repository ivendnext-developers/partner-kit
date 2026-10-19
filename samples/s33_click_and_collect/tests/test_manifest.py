"""S33's laptop tests: the manifest passes the kit's checker, its two fields can be set after a delivery note is submitted
and *Handed over* is a list column and filter (the Delivery Note list filtered on it is the waiting list), its report lists
exactly the web orders to pick, its workspace opens the sales orders and the delivery notes (never its own report), and nothing leaves the shop. The
shop's install refuses a report that names a field the same manifest adds, and so does the kit (site_rules.py). Data only: no service.

    python3 -m unittest discover -s samples/s33_click_and_collect/tests -p 'test_*.py'
"""
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "manifest"))
import site_rules  # noqa: E402
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
PICK = "PP CCB Web Orders To Pick"
OUTSIDE = ("extension_subscriptions", "webhooks", "registered_applications", "remote_keys", "desk_actions")


def report(name):
    return next(r for r in MANIFEST["reports"] if r["name"] == name)


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])
        self.assertEqual(site_rules.refusals(MANIFEST), [])   # nor anything the shop's install refuses

    def test_the_two_fields_are_on_the_delivery_note_and_settable_after_submit(self):
        fields = {f["fieldname"]: f for f in MANIFEST["custom_fields"]}
        self.assertEqual(set(fields), {"pp_ccb_handed_over", "pp_ccb_collected_by"})
        for f in fields.values():
            self.assertEqual(f["dt"], "Delivery Note")
            self.assertEqual(f.get("allow_on_submit"), 1, f["fieldname"])   # a submitted note is where they are set
            self.assertNotIn("default", f)
        self.assertEqual(fields["pp_ccb_handed_over"]["fieldtype"], "Check")

    def test_handed_over_is_a_list_column_and_a_list_filter_so_the_list_is_the_waiting_list(self):
        f = next(f for f in MANIFEST["custom_fields"] if f["fieldname"] == "pp_ccb_handed_over")
        self.assertEqual((f.get("in_list_view"), f.get("in_standard_filter")), (1, 1))

    def test_web_orders_to_pick_are_submitted_sales_orders_still_to_deliver_with_a_web_order_number(self):
        r = report(PICK)
        self.assertEqual((r["ref_doctype"], r["report_type"]), ("Sales Order", "Report Builder"))
        self.assertCountEqual(r["filters"], [["docstatus", "=", 1], ["status", "in", ["To Deliver and Bill", "To Deliver"]],
                                             ["po_no", "is", "set"]])
        self.assertIn("set_warehouse", r["columns"])     # the store, so each store filters its own

    def test_no_report_names_a_field_this_manifest_adds(self):
        added = {f["fieldname"] for f in MANIFEST["custom_fields"]}
        for r in MANIFEST["reports"]:
            named = set(r["columns"]) | {f[0] for f in r["filters"]}
            self.assertFalse(named & added, r["name"])     # the shop refuses it at install (live record type)

    def test_the_workspace_opens_the_two_lists_and_never_its_own_report(self):
        ws = MANIFEST["workspaces"][0]
        targets = {(s["type"], s["link_to"]) for s in ws["shortcuts"]}
        self.assertEqual(targets, {("DocType", "Sales Order"), ("DocType", "Delivery Note")})
        # the shop makes a workspace before the manifest's reports, so a shortcut to PICK fails at install (APPF run 5)
        self.assertNotIn(("Report", PICK), targets)
        line = next(b["data"]["text"] for b in ws["blocks"] if b["type"] == "paragraph")
        self.assertIn("Web orders to pick", line)        # the line names the report to search for
        labels = {s["label"] for s in ws["shortcuts"]}
        placed = {b["data"]["shortcut_name"] for b in ws["blocks"] if b["type"] == "shortcut"}
        self.assertEqual(placed, labels)                  # every shortcut is placed on the page

    def test_nothing_leaves_the_shop(self):
        self.assertEqual(MANIFEST.get("allowed_urls"), [])
        for kind in OUTSIDE:
            self.assertFalse(MANIFEST.get(kind), kind)
        self.assertNotIn("doctypes", MANIFEST)            # no record type of its own: nothing to export but the fields

    def test_the_checker_refuses_what_the_product_would(self):
        m = copy.deepcopy(MANIFEST)
        m["custom_fields"][0]["default"] = "1"
        self.assertTrue(validate.validate(m), "a default on a field of a shop's own record type")
        m = copy.deepcopy(MANIFEST)
        m["reports"][0]["report_type"] = "Query Report"
        self.assertTrue(any("Report Builder" in r["reason"] for r in validate.validate(m)))
        m = copy.deepcopy(MANIFEST)                       # the waiting list as a report: the shop refused it (APPF run 5)
        m["reports"].append({"name": "PP CCB Waiting For Collection", "ref_doctype": "Delivery Note",
                             "report_type": "Report Builder", "columns": ["name", "pp_ccb_collected_by"],
                             "filters": [["docstatus", "=", 1], ["pp_ccb_handed_over", "=", 0]]})
        self.assertTrue(any("not fields of Delivery Note" in r["reason"] for r in site_rules.refusals(m)))
        m = copy.deepcopy(MANIFEST)                       # a shortcut to its own report: the shop refused it (APPF run 5)
        m["workspaces"][0]["shortcuts"].append({"type": "Report", "link_to": PICK, "label": "Pick"})
        self.assertTrue(any("Link To: " + PICK in r["reason"] for r in site_rules.refusals(m)))


if __name__ == "__main__":
    unittest.main()
