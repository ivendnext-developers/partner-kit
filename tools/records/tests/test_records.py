"""The record-type generator: the merge the site makes, the words it refuses, the census and the snapshot check.

    python3 -m unittest discover -s tools/records/tests -p 'test_*.py'

Offline: a recorded record-type definition stands in for the site (a definition, one added field, one change to a field).
"""

import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "records"))
import records  # noqa: E402

WORD = "ERP" + "Next"                                  # built from parts, so this file does not contain either word
CODE = "fr" + "appe" + ".client.get_list"

DEFINITION = {
    "name": "Warranty Claim", "is_submittable": 1, "issingle": 0, "istable": 0, "description": "",
    "fields": [
        {"idx": 1, "fieldname": "customer", "label": "Customer", "fieldtype": "Link", "options": "Customer", "reqd": 1},
        {"idx": 2, "fieldname": "sb1", "label": "", "fieldtype": "Section Break"},
        {"idx": 3, "fieldname": "status", "label": "Status", "fieldtype": "Select", "options": "Open\nClosed"},
        {"idx": 4, "fieldname": "cb1", "fieldtype": "Column Break"},
        {"idx": 5, "fieldname": "notes", "label": "Notes", "fieldtype": "Small Text",
         "description": f"Kept as {WORD} keeps any note."},
        {"idx": 6, "fieldname": "lines", "label": "Lines", "fieldtype": "Table", "options": "Warranty Claim Line"},
    ],
}
CHILD = {"name": "Warranty Claim Line", "istable": 1, "fields": [
    {"idx": 1, "fieldname": "item_code", "label": "Item", "fieldtype": "Link", "options": "Item", "reqd": 1},
    {"idx": 2, "fieldname": "qty", "label": "Quantity", "fieldtype": "Float", "description": f"Read with {CODE}."}]}
CUSTOM = [{"idx": 1, "fieldname": "store_ref", "label": "Store reference", "fieldtype": "Data", "insert_after": "customer",
           "read_only": 1}]
PROPS = [{"doctype_or_field": "DocField", "field_name": "status", "property": "reqd", "value": "1"},
         {"doctype_or_field": "DocField", "field_name": "notes", "property": "hidden", "value": "1"},
         {"doctype_or_field": "DocType", "field_name": "", "property": "title_field", "value": "customer"}]


class FakeSite(records.Site):
    """The site's reads, from the recorded definitions above (the merge's own filter is tested apart)."""
    def __init__(self):
        pass
    def get(self, path, **params):                      # the list of every record type on the site
        return [{"name": "Warranty Claim", "module": "Selling", "istable": 0, "issingle": 0, "custom": 0},
                {"name": "PP WRC Claim", "module": "Pp Wrc", "istable": 0, "issingle": 0, "custom": 1}]

    def definition(self, name):
        return {"Warranty Claim": (DEFINITION, CUSTOM, PROPS), "Warranty Claim Line": (CHILD, [], [])}[name]


class Merge(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.rec = records.merge(DEFINITION, CUSTOM, PROPS, self.log)
        self.by = {f["fieldname"]: f for f in self.rec["fields"]}

    def test_the_added_field_is_merged_after_the_field_it_names(self):
        self.assertEqual([f["fieldname"] for f in self.rec["fields"]], ["customer", "store_ref", "status", "notes", "lines"])
        self.assertEqual(self.by["store_ref"]["added"], 1)
        self.assertEqual(self.by["store_ref"]["read_only"], 1)

    def test_a_change_to_a_field_is_merged(self):
        self.assertEqual(self.by["status"]["required"], 1)          # not required in the definition, required by the change
        self.assertEqual(self.by["notes"]["hidden"], 1)

    def test_without_the_merge_the_page_would_be_wrong(self):    # the canary: the merge is what makes these true
        bare = {f["fieldname"]: f for f in records.merge(DEFINITION, [], [], [])["fields"]}
        self.assertNotIn("store_ref", bare)
        self.assertEqual(bare["status"]["required"], 0)

    def test_layout_rows_are_dropped(self):
        self.assertNotIn("sb1", self.by)
        self.assertNotIn("cb1", self.by)

    def test_links_and_choices(self):
        self.assertEqual(self.by["customer"]["links_to"], "Customer")
        self.assertEqual(self.by["lines"]["links_to"], "Warranty Claim Line")
        self.assertEqual(self.by["status"]["choices"], ["Open", "Closed"])
        self.assertEqual(self.rec["submittable"], 1)


class ProductOnly(unittest.TestCase):
    MODULES = {"Stock": "erpnext", "iVendNext mPOS": "ivendnext_mpos", "Pp Bln": "pp_bln"}

    def test_a_samples_or_a_hand_made_field_is_left_out(self):      # the canary: a sample's field must not reach the pages
        rows = [{"fieldname": "custom_gift_card_master", "module": "iVendNext mPOS"},
                {"fieldname": "pp_bln_default_bin", "module": "Pp Bln"},
                {"fieldname": "custom_test_note", "module": None}]
        self.assertEqual([r["fieldname"] for r in records.product_only(rows, self.MODULES)], ["custom_gift_card_master"])

    def test_the_kits_snapshots_hold_no_samples_field(self):
        for p in (ROOT / "api" / "records").glob("*.json"):
            text = p.read_text("utf-8")
            self.assertNotIn('"fieldname": "pp_', text, p.name)


class Words(unittest.TestCase):
    def test_the_name_used_as_a_word_becomes_ivendnext(self):
        rec = records.merge(DEFINITION, CUSTOM, PROPS, [])
        notes = next(f for f in rec["fields"] if f["fieldname"] == "notes")
        self.assertEqual(notes["description"], "Kept as iVendNext keeps any note.")

    def test_a_name_in_code_is_dropped_and_logged(self):
        log = []
        rec = records.merge(CHILD, [], [], log)
        self.assertEqual(rec["fields"][1]["description"], "")
        self.assertTrue(any("qty description: dropped" in line for line in log), log)

    def test_the_writer_refuses_a_snapshot_that_still_names_one(self):     # the canary: a word in a description is refused
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(ValueError, "refused"):
                records.write_json(pathlib.Path(d) / "x.json", {"fields": [{"description": f"See {CODE}"}]})
            self.assertFalse((pathlib.Path(d) / "x.json").exists())

    def test_a_field_whose_name_names_one_is_dropped(self):
        log = []
        bad = dict(DEFINITION, fields=[{"idx": 1, "fieldname": WORD.lower() + "_ref", "label": "Ref", "fieldtype": "Data"}])
        self.assertEqual(records.merge(bad, [], [], log)["fields"], [])
        self.assertTrue(log)


class Fetch(unittest.TestCase):
    def test_a_snapshot_carries_its_tables(self):
        rec = records.snapshot(FakeSite(), "Warranty Claim", [])
        self.assertEqual(list(rec["tables"]), ["Warranty Claim Line"])
        self.assertEqual(rec["tables"]["Warranty Claim Line"]["fields"][0]["links_to"], "Item")

    def test_fetch_writes_one_file_per_listed_record_type_and_the_index(self):
        saved = records.RECORDS
        records.RECORDS = [("Warranty Claim", "Sales and returns", True, "A claim.")]
        try:
            with tempfile.TemporaryDirectory() as d:
                out = pathlib.Path(d)
                records.fetch(FakeSite(), out, release="test")
                self.assertEqual(sorted(p.name for p in out.glob("*.json")), ["index.json", "site_record_types.json", "warranty_claim.json"])
                kept = json.loads((out / "site_record_types.json").read_text("utf-8"))["record_types"]
                self.assertEqual([t["name"] for t in kept], ["Warranty Claim"])          # a site's custom record type is left out
                self.assertEqual(records.check_faults(out), [])
                rec = json.loads((out / "warranty_claim.json").read_text("utf-8"))
                self.assertIn("retail core", rec["why"])
                (out / "warranty_claim.json").unlink()                 # the canary: a missing snapshot is a fault
                self.assertTrue(any("missing" in b for b in records.check_faults(out)))
        finally:
            records.RECORDS = saved


class Census(unittest.TestCase):
    def kit(self, d: str, text: str) -> pathlib.Path:
        root = pathlib.Path(d)
        (root / "recipes").mkdir()
        (root / "recipes" / "x.md").write_text(text, "utf-8")
        return root

    def test_the_kit_census_is_clean(self):                          # the narrow census: addresses and manifests
        self.assertEqual(records.census_faults(wide=False), [])

    def test_the_kits_own_snapshots_match_the_list(self):            # a record type listed without a fetch is red here
        self.assertEqual(records.check_faults(), [])

    def test_a_record_type_the_kit_names_but_the_list_does_not_is_a_fault(self):    # the canary
        with tempfile.TemporaryDirectory() as d:
            root = self.kit(d, "Read `GET /api/resource/Shipping%20Rule/<name>` and /api/resource/Item.")
            faults = records.census_faults(root)
            self.assertTrue(any(f.startswith("Shipping Rule: named by recipes/x.md") for f in faults), faults)
            self.assertFalse(any(f.startswith("Item:") for f in faults), faults)

    def test_placeholders_and_made_up_names_are_not_record_types(self):
        with tempfile.TemporaryDirectory() as d:
            root = self.kit(d, "/api/resource/{record_type} · /api/resource/PP WRC Claim · /api/v2/document/Stock%20Entry/x")
            named = records.named_by_kit(root)
            self.assertEqual(sorted(named), ["Stock Entry"])

    def test_every_record_type_in_the_api_description_is_listed(self):
        listed = {r[0] for r in records.RECORDS}
        spec = (ROOT / "api" / "openapi.yaml").read_text("utf-8")
        named = {records.urllib.parse.unquote(n).strip() for n in records.ADDRESS.findall(spec)}
        self.assertTrue(named)
        self.assertEqual(sorted(named - listed), [])


if __name__ == "__main__":
    unittest.main()
