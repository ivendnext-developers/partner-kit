"""S33's laptop tests: the manifest passes the kit's checker, its two fields can be set after a delivery note is submitted
and *Handed over* is a list column and filter (the Delivery Note list filtered on it is the waiting list), its report lists
exactly the web orders to pick and opens for the store manager and the stock clerk, its workspace opens the report, the sales orders and the delivery notes, and nothing leaves the shop. The
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
        # the Details tab's first section, where the counter sees them; never the folded More Info (after po_no)
        self.assertEqual(fields["pp_ccb_handed_over"]["insert_after"], "return_against")

    def test_handed_over_is_a_list_column_and_a_list_filter_so_the_list_is_the_waiting_list(self):
        f = next(f for f in MANIFEST["custom_fields"] if f["fieldname"] == "pp_ccb_handed_over")
        self.assertEqual((f.get("in_list_view"), f.get("in_standard_filter")), (1, 1))

    def test_the_waiting_list_leaves_out_an_order_the_till_handed_over(self):
        ws = json.dumps(MANIFEST["workspaces"]) + MANIFEST["description"]
        self.assertEqual(ws.count("POS Pickup Handed At not set"), 2)   # the till writes that field, not Handed over

    def test_web_orders_to_pick_are_submitted_sales_orders_still_to_deliver_with_a_web_order_number(self):
        r = report(PICK)
        self.assertEqual((r["ref_doctype"], r["report_type"]), ("Sales Order", "Report Builder"))
        self.assertCountEqual(r["filters"], [["docstatus", "=", 1], ["status", "in", ["To Deliver and Bill", "To Deliver"]],
                                             ["po_no", "is", "set"]])
        self.assertIn("set_warehouse", r["columns"])     # the store, so each store filters its own

    def test_the_report_and_its_page_open_for_the_store_manager_and_the_stock_clerk(self):
        # the installer opens the app's page for the roles the manifest names (and the administrator): none named,
        # the store manager and the stock clerk meet Page not found. Naming roles replaces the engine's own Sales Order
        # readers on the report, so the sales desk that takes web orders is named too.
        self.assertCountEqual(report(PICK)["roles"], ["Retail Manager", "Stock User", "Stock Manager", "Sales User", "Sales Manager", "System Manager"])

    def test_no_report_names_a_field_this_manifest_adds(self):
        added = {f["fieldname"] for f in MANIFEST["custom_fields"]}
        for r in MANIFEST["reports"]:
            named = set(r["columns"]) | {f[0] for f in r["filters"]}
            self.assertFalse(named & added, r["name"])     # the shop refuses it at install (live record type)

    def test_the_workspace_opens_the_report_and_the_two_lists(self):
        ws = MANIFEST["workspaces"][0]
        targets = {(s["type"], s["link_to"]) for s in ws["shortcuts"]}
        # the installer makes the pages after the reports, so a shortcut may open the app's own report
        self.assertEqual(targets, {("Report", PICK), ("DocType", "Sales Order"), ("DocType", "Delivery Note")})
        line = next(b["data"]["text"] for b in ws["blocks"] if b["type"] == "paragraph")
        self.assertIn("open Web orders to pick", line)   # the line points at the report's shortcut
        self.assertNotIn("search Desk", line)
        labels = {s["label"] for s in ws["shortcuts"]}
        placed = {b["data"]["shortcut_name"] for b in ws["blocks"] if b["type"] == "shortcut"}
        self.assertEqual(placed, labels)                  # every shortcut is placed on the page

    def test_nothing_leaves_the_shop(self):
        self.assertEqual(MANIFEST.get("allowed_urls"), [])
        for kind in OUTSIDE:
            self.assertFalse(MANIFEST.get(kind), kind)
        self.assertNotIn("doctypes", MANIFEST)            # no record type of its own: nothing to export but the fields

    def test_desk_shows_the_page_and_the_report_by_their_plain_names(self):
        words = next(t["words"] for t in MANIFEST["translations"] if t["language"] == "en")
        self.assertEqual(words, {"PP CCB Click and collect": "Click and collect", PICK: "Web orders to pick"})

    def test_the_checker_refuses_what_the_product_would(self):
        m = copy.deepcopy(MANIFEST)
        m["custom_fields"][0]["default"] = "1"
        self.assertTrue(validate.validate(m), "a default on a field of a shop's own record type")
        m = copy.deepcopy(MANIFEST)
        m["reports"][0]["report_type"] = "Query Report"
        self.assertTrue(any("Report Builder" in r["reason"] for r in validate.validate(m)))


if __name__ == "__main__":
    unittest.main()
