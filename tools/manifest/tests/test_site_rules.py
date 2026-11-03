"""tools/manifest/site_rules.py: what the shop's install stops on that its checker passes — stdlib only:
    python3 -m unittest discover -s tools/manifest/tests -v

The base is S33's manifest, which passes both."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from site_rules import refusals as site  # noqa: E402
from validate import validate  # noqa: E402

BASE = json.loads((HERE.parents[2] / "samples" / "s33_click_and_collect" / "manifest.json").read_text())
ADDED = "pp_ccb_handed_over"           # a field BASE adds to the shop's Delivery Note


class WhatItNoLongerStops(unittest.TestCase):
    def test_the_base_passes_both(self):
        self.assertEqual((validate(BASE), site(BASE)), ([], []))

    def test_a_report_on_a_field_it_adds_and_a_workspace_on_its_own_report_pass(self):
        # both installed on the test bench at POS build 2.1.0.679
        m = copy.deepcopy(BASE)
        m["reports"].append({"name": "PP CCB Waiting", "ref_doctype": "Delivery Note", "columns": ["name", ADDED], "filters": [[ADDED, "=", 0]]})
        m["workspaces"] = [{"name": "PP CCB Home", "shortcuts": [{"type": "Report", "link_to": "PP CCB Waiting"}]}]
        self.assertEqual(site(m), [])


class FeedDescription(unittest.TestCase):
    """The shop's Registered Application keeps 140 characters of description."""

    def test_a_feed_description_over_140_characters_is_refused_and_140_passes(self):
        m = copy.deepcopy(BASE)
        reg = m.setdefault("registered_applications", [{"name": "PP CCB feed", "events": ["Delivery Note"]}])[0]
        reg["description"] = "x" * 140
        self.assertEqual([r for r in site(m) if "description" in r["reason"]], [])
        reg["description"] = "x" * 141
        self.assertEqual(validate(m), [])                 # the shop's checker passes it: only the install refuses it
        self.assertTrue(any("141 characters" in r["reason"] for r in site(m)))

    def test_a_dynamic_link_must_name_a_link_field_to_doctype_or_a_select(self):
        m = {"doctypes": [{"name": "PP X Row", "istable": 1, "fields": [
            {"fieldname": "kind", "fieldtype": "Data"}, {"fieldname": "ref", "fieldtype": "Dynamic Link", "options": "kind"}]}]}
        self.assertTrue(any("Dynamic Link" in r["reason"] for r in site(m)))
        m["doctypes"][0]["fields"][0] = {"fieldname": "kind", "fieldtype": "Link", "options": "Item"}
        self.assertTrue(any("Dynamic Link" in r["reason"] for r in site(m)))
        for ok in ({"fieldtype": "Link", "options": "DocType"}, {"fieldtype": "Select", "options": "POS Invoice\nSales Invoice"}):
            m["doctypes"][0]["fields"][0] = dict(ok, fieldname="kind")
            self.assertEqual(site(m), [], ok)

    def test_every_sample_feed_description_fits(self):
        for f in sorted((HERE.parents[2] / "samples").glob("*/manifest.json")):
            bad = [r for r in site(json.loads(f.read_text())) if "description" in r["reason"]]
            self.assertEqual(bad, [], f.parent.name)


if __name__ == "__main__":
    unittest.main()
