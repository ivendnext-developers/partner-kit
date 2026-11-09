"""S54's manifest: a run with its stores, its rows written only by the app's role, one button on the run for the buyers
sending no more than its name, a report over the rows, and the address the service's.

    python3 -m unittest discover -s samples/s54_sell_through/tests -p 'test_*.py'
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
MANIFEST = os.path.join(SAMPLE, "manifest.json")
sys.path[:0] = [SAMPLE, os.path.join(SAMPLE, "service")]
import sst  # noqa: E402

sys.path.insert(0, os.path.join(SAMPLE, "..", "..", "tools", "manifest"))
from validate import validate  # noqa: E402

FEED = {"name": "PP SST Sell-through feed",
        "description": "the sell-through service reads the two reports and the items and writes the rows as this user",
        "events": ["PP SST Sell-through"]}


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.types = {d["name"]: d for d in self.m["doctypes"]}
        self.run = {f["fieldname"]: f for f in self.types[sst.RUN]["fields"]}
        self.row = {f["fieldname"]: f for f in self.types[sst.ROW]["fields"]}

    def test_three_record_types_two_tables(self):
        self.assertEqual(sorted(self.types), sorted([sst.RUN, sst.ROW, sst.STORE]))
        self.assertTrue(self.types[sst.ROW].get("istable") and self.types[sst.STORE].get("istable"))
        self.assertEqual((self.run["stores"]["options"], self.run["rows"]["options"]), (sst.STORE, sst.ROW))
        self.assertFalse(self.run["stores"].get("reqd"))     # a child table is never reqd; the press asks for a store
        self.assertEqual(self.types[sst.RUN]["autoname"], "format:SST-{#####}")

    def test_the_runs_fields_are_the_ones_the_service_reads_and_writes(self):
        read = {"item_group", "style", "sold_since", "size_attribute", "colour_attribute", "stores"}
        written = {"rows", "summary"}
        self.assertEqual(set(self.run) - {"title", "column_attributes", "section_result"}, read | written)
        self.assertTrue(all(self.run[f].get("read_only") for f in written))
        self.assertTrue(all(self.run[f].get("reqd") for f in ("item_group", "sold_since", "size_attribute")))
        self.assertEqual((self.run["size_attribute"]["options"], self.run["colour_attribute"]["options"]),
                         ("Item Attribute", "Item Attribute"))

    def test_a_row_holds_what_rows_of_writes_and_is_read_only(self):
        run = sst.Run("R", "G", "", __import__("datetime").date(2026, 10, 1), "Size", "", ["S1"])
        (r,) = sst.rows_of({"I": {"style": "T", "size": "M", "colour": ""}}, {"S1": {"I": 1}}, {}, run, {}, {})
        self.assertEqual(set(r), set(self.row))
        self.assertTrue(all(f.get("read_only") for f in self.row.values()))
        self.assertFalse(self.row["none_left"].get("in_standard_filter"))   # a Check is never a standard filter

    def test_only_the_apps_role_writes_without_creating_and_buyers_keep_the_runs(self):
        perms = {p["role"]: p for p in self.types[sst.RUN]["permissions"]}
        self.assertEqual(sorted(k for k, v in perms["PP SST Integration"].items() if v == 1), ["read", "write"])
        self.assertEqual(sorted(perms), sorted(["PP SST Integration", "Sales Manager", "Stock Manager", "System Manager"]))

    def test_the_button_is_on_the_run_for_the_buyers_and_sends_only_its_name(self):
        (a,) = self.m["desk_actions"]
        self.assertEqual((a["record_type"], a["label"], a["placement"], a["service"], a["send_fields"]),
                         (sst.RUN, "Work out sell-through", "form", "work", "name"))
        perms = {p["role"] for p in self.types[sst.RUN]["permissions"] if p.get("read")}
        self.assertLessEqual(set(a["roles"]), perms)       # a press re-checks the user's read on the record (run 10)
        (s,) = self.m["extension_subscriptions"]
        self.assertEqual((s["key"], s["point"], s["timeout_seconds"]), ("work", "desk_action", 10))
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"]])
        self.assertTrue(s["endpoint_url"].endswith("/sst/work"))

    def test_the_report_reads_the_rows_only(self):
        (r,) = self.m["reports"]
        self.assertEqual(r["ref_doctype"], sst.RUN)
        self.assertEqual({c.split(".")[0] for c in r["columns"] if "." in c}, {"rows"})
        self.assertTrue({c.split(".")[1] for c in r["columns"] if "." in c} <= set(self.row))

    def test_the_install_gives_the_role_the_two_reports_and_the_rights_they_ask_for(self):
        role = "PP SST Integration"
        rights = {e["doctype"]: e["rights"] for e in self.m["role_rights"] if "doctype" in e}
        reports = [e["report"] for e in self.m["role_rights"] if "report" in e]
        self.assertTrue(all(e["role"] == role for e in self.m["role_rights"]))
        self.assertEqual(sorted(reports), sorted([sst.POS_SALE_REPORT, sst.STOCK_REPORT]))   # the two the service runs, by the names it runs
        self.assertTrue(all(set(e) == {"report", "role"} for e in self.m["role_rights"] if "report" in e))   # a report entry takes no rights
        self.assertEqual(rights["POS Invoice"], ["read", "report"])
        self.assertEqual([d for d, r in rights.items() if r == ["read"]], ["Item", "Item Attribute", "Warehouse", "UOM"])
        self.assertEqual([d for d, r in rights.items() if r == ["select"]], ["POS Profile", "Item Group", "Customer", "Customer Group"])
        self.assertEqual(len(rights), 9)                    # one entry per record type, as the install refuses two
        self.assertEqual(validate(self.m), [])              # and the kit's copy of the shop's own checker takes the whole manifest

    def test_the_feed_registration_is_frozen(self):
        (f,) = self.m["registered_applications"]
        self.assertEqual(f, FEED)                           # an update refuses a changed one (APPFV 3)
        self.assertLessEqual(len(f["description"]), 140)

    def test_the_help_address_names_the_recipes_section(self):
        (p,) = self.m["property_setters"]
        self.assertEqual((p["doc_type"], p["property"]), (sst.RUN, "documentation"))
        self.assertTrue(p["value"].endswith("shop_reports.html#sell-through-by-size-and-colour"))


if __name__ == "__main__":
    unittest.main()
