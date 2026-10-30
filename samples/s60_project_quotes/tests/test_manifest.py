"""S60's laptop tests: the manifest passes the kit's checker and nothing the retailer's install refuses; the app calls
no outside address and holds no money; the project field is the same Link on all five documents a builder's job runs
through, and the stage field the same text field on the three line tables, so Desk's own Create (which copies a field
of the same name, unless it is no_copy) carries both from the quote to the order, each delivery and the invoice; both are
optional and settable after submit where a booked document needs them; the project's builder is required and its name
a read-only copy; no table is required; the project sheet reads each document type through ivn_rows (the viewer's
rights) filtered on the project, never through the framework's own readers, and prints the retailer's letter head; the
builder's projects under Customer; the rights and the help page. Data only: no service.

    python3 -m unittest discover -s samples/s60_project_quotes/tests -p 'test_*.py'
"""
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "manifest"))
import site_rules  # noqa: E402
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
P = MANIFEST["prefix"]
PROJECT, STAGE = f"{P} Project", f"{P} Stage"
DT = {d["name"]: d for d in MANIFEST["doctypes"]}
OUTSIDE = ("extension_subscriptions", "webhooks", "registered_applications", "remote_keys", "desk_actions")
HEADERS = {"Quotation", "Sales Order", "Delivery Note", "Sales Invoice", "POS Invoice"}
LINES = {"Quotation Item", "Sales Order Item", "Delivery Note Item"}
(PF,) = MANIFEST["print_formats"]


def fields(dt):
    return {f["fieldname"]: f for f in DT[dt]["fields"]}


def rights(role):
    row = next(p for p in DT[PROJECT]["permissions"] if p["role"] == role)
    return {k for k, v in row.items() if k != "role" and v}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])
        self.assertEqual(site_rules.refusals(MANIFEST), [])   # nor anything the retailer's install refuses

    def test_no_outside_address_no_money_no_rule_of_its_own(self):
        self.assertEqual(MANIFEST["allowed_urls"], [])
        self.assertFalse([k for k in OUTSIDE if MANIFEST.get(k)])          # no service, feed, key or Desk action
        money = [(d, f["fieldname"]) for d in DT for f in DT[d]["fields"] if f["fieldtype"] in ("Currency", "Percent")]
        self.assertEqual(money, [])                                        # the till and the ERP keep the money
        self.assertFalse(MANIFEST.get("workflows") or MANIFEST.get("save_rules") or MANIFEST.get("reports"))

    def test_the_project_field_is_one_optional_link_on_the_five_documents_carried_by_create(self):
        got = [c for c in MANIFEST["custom_fields"] if c["fieldtype"] == "Link"]
        self.assertEqual({c["dt"] for c in got}, HEADERS)
        self.assertEqual(len(got), len(HEADERS))
        self.assertEqual({c["fieldname"] for c in got}, {MANIFEST["app"] + "_project"})   # one name: Create copies it
        for c in got:
            self.assertEqual(c["options"], PROJECT)
            self.assertFalse(c.get("reqd") or c.get("no_copy") or c.get("read_only") or c.get("hidden") or c.get("default"))
            self.assertEqual(c.get("allow_on_submit"), 1, c["dt"])         # a booked till sale or order is named later

    def test_the_stage_field_is_one_optional_text_field_on_the_three_line_tables(self):
        got = [c for c in MANIFEST["custom_fields"] if c["dt"] in LINES]
        self.assertEqual({c["dt"] for c in got}, LINES)
        self.assertEqual(len(got), len(LINES))
        self.assertEqual({c["fieldname"] for c in got}, {MANIFEST["app"] + "_stage"})
        for c in got:
            self.assertEqual(c["fieldtype"], "Data")
            self.assertFalse(c.get("reqd") or c.get("no_copy") or c.get("read_only") or c.get("hidden"))
        so = next(c for c in got if c["dt"] == "Sales Order Item")
        self.assertEqual(so.get("allow_on_submit"), 1)                      # renamed on a submitted order's line
        self.assertEqual(so["insert_after"], "delivery_date")               # beside the line's own date
        self.assertEqual(len(MANIFEST["custom_fields"]), len(HEADERS) + len(LINES))

    def test_the_builder_is_required_and_its_name_a_read_only_copy(self):
        f = fields(PROJECT)
        self.assertEqual((f["customer"]["fieldtype"], f["customer"]["options"], f["customer"].get("reqd")),
                         ("Link", "Customer", 1))
        self.assertEqual((f["customer_name"].get("fetch_from"), f["customer_name"].get("read_only")),
                         ("customer.customer_name", 1))
        self.assertEqual(f["status"]["options"].split("\n"), ["Open", "Completed", "Cancelled"])
        self.assertEqual(f["status"].get("default"), "Open")
        self.assertEqual(DT[PROJECT]["title_field"], "project_name")
        self.assertEqual(DT[STAGE].get("istable"), 1)

    def test_no_table_is_ever_required(self):
        for d in DT.values():
            for f in d["fields"]:
                if f["fieldtype"] == "Table":
                    self.assertFalse(f.get("reqd"), f["fieldname"])

    def test_the_sheet_reads_each_document_with_the_viewers_rights_filtered_on_the_project(self):
        html = PF["html"]
        self.assertEqual((PF["doc_type"], PF["print_format_type"]), (PROJECT, "Jinja"))
        reads = re.findall(r'ivn_rows\("([^"]+)", filters=\{"([a-z_]+)": doc\.name\}', html)
        self.assertEqual(sorted(t for t, _ in reads), sorted(HEADERS))
        self.assertEqual({f for _, f in reads}, {MANIFEST["app"] + "_project"})
        self.assertNotRegex(html, r"\b(get_all|get_list|get_doc|get_value|db\.)")   # never the framework's own readers
        self.assertIn("{{ letter_head }}", html)                            # a Jinja print places it itself (run 22)
        own = set(fields(PROJECT)) | {"name", "status"}
        self.assertFalse({m for m in re.findall(r"doc\.([a-z_]+)", html)} - own - {"get_formatted"})
        self.assertFalse({m for m in re.findall(r"\bs\.([a-z_]+)", html)} - set(fields(STAGE)) - {"get_formatted"})
        self.assertEqual(len(re.findall(r"None yet\.", html)), len(HEADERS))   # an empty section still reads well

    def test_the_builder_lists_its_projects(self):
        got = {(ln["doctype"], ln["link_doctype"], ln["link_fieldname"]) for ln in MANIFEST["links"]}
        self.assertEqual(got, {("Customer", PROJECT, "customer")})

    def test_the_trade_desk_keeps_projects_no_one_but_a_system_manager_deletes(self):
        self.assertEqual(rights("Sales User"), {"read", "write", "create", "report", "print"})
        self.assertNotIn("delete", rights("Sales Manager"))
        self.assertIn("delete", rights("System Manager"))
        self.assertEqual(rights("Stock User"), {"read", "report"})
        self.assertEqual(rights("Accounts User"), {"read"})
        self.assertEqual(rights("Retail Manager"), {"read", "report", "print"})   # names a till document's project

    def test_the_project_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (PROJECT, "documentation"))
        self.assertTrue(ps["value"].endswith("project_quotes.html#projects"))


if __name__ == "__main__":
    unittest.main()
