"""tools/manifest/site_rules.py: what the shop's install refuses that its checker passes — stdlib only:
    python3 -m unittest discover -s tools/manifest/tests -v

A report, number card or chart may not name a field the same manifest adds to a shop's record type, and a workspace may
not link the manifest's own report.

The shop's install checks those fields against the record type as it is BEFORE the install (POS
``manifest_install._site_refusals_v2`` ``fields_exist``: a report's columns and filter fields, a card's
``aggregate_function_based_on``, a chart's four fields), so such a manifest is refused at a shop although it looks whole.
Found on our test bench by APPF run 5 (S33's first manifest). The base is S33's manifest, which passes."""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from site_rules import CHART_FIELDS, refusals as site  # noqa: E402
from validate import validate  # noqa: E402

BASE = json.loads((HERE.parents[2] / "samples" / "s33_click_and_collect" / "manifest.json").read_text())
ADDED = "pp_ccb_handed_over"           # a field BASE adds to the shop's Delivery Note


def refused(change) -> list:
    m = copy.deepcopy(BASE)
    change(m)
    return [r["reason"] for r in site(m) if "not fields of Delivery Note" in r["reason"]]


class OwnAddedFields(unittest.TestCase):
    def test_the_base_passes_both(self):
        self.assertEqual((validate(BASE), site(BASE)), ([], []))

    def test_a_report_column_or_filter_on_an_added_field_is_refused(self):
        rep = {"name": "PP CCB Waiting", "ref_doctype": "Delivery Note", "columns": ["name"], "filters": []}
        self.assertTrue(refused(lambda m: m["reports"].append(dict(rep, columns=["name", ADDED]))))
        self.assertTrue(refused(lambda m: m["reports"].append(dict(rep, filters=[[ADDED, "=", 0]]))))

    def test_a_number_card_or_chart_field_on_an_added_field_is_refused(self):
        card = {"name": "PP CCB Count", "document_type": "Delivery Note", "function": "Sum",
                "aggregate_function_based_on": ADDED}
        self.assertTrue(refused(lambda m: m.update(number_cards=[card])))
        for k in CHART_FIELDS:     # each of the four fields the shop checks
            chart = {"name": "PP CCB Chart", "document_type": "Delivery Note", "chart_type": "Group By", k: ADDED, "type": "Bar"}
            self.assertTrue(refused(lambda m, c=chart: m.update(dashboard_charts=[c])), k)

    def test_a_workspace_shortcut_to_its_own_report_is_refused(self):
        # the shop makes workspaces before reports, so the link to a report the same manifest makes cannot save
        sc = {"type": "Report", "link_to": BASE["reports"][0]["name"], "label": "Pick"}
        m = copy.deepcopy(BASE)
        m["workspaces"][0]["shortcuts"].append(sc)
        self.assertEqual(validate(m), [])                 # the shop's checker passes it: only the install refuses it
        self.assertTrue(any("Link To: " + sc["link_to"] in r["reason"] for r in site(m)))
        m["workspaces"][0]["shortcuts"][-1] = dict(sc, link_to="Stock Ledger")     # a report the shop already has
        self.assertFalse(any("Link To:" in r["reason"] for r in site(m)))

    def test_what_the_shop_does_not_check_is_not_refused(self):
        # a card's FILTERS are not checked by the shop's install, and a standard field is always there
        card = {"name": "PP CCB Count", "document_type": "Delivery Note", "filters": [[ADDED, "=", 0]]}
        self.assertEqual(refused(lambda m: m.update(number_cards=[card])), [])
        rep = {"name": "PP CCB Notes", "ref_doctype": "Delivery Note", "columns": ["name", "po_no"],
               "filters": [["is_return", "=", 0]]}
        self.assertEqual(refused(lambda m: m["reports"].append(rep)), [])


if __name__ == "__main__":
    unittest.main()
