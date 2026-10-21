# COPY — source: repo ivendnext/iVendNext_PWA, path apps/ivendnext_mpos/ivendnext_mpos/tests/test_manifest_check_reportcols.py,
# at development 7d47d331a203fd8b2794f83270a4190b3c1908e8; changed: the import, the fixture folder, and the lane id in the docstring and in its fixture's description.
# A defect here is a defect there: report it with the Kit defect form (feedback/README.md).
"""P-REPORTCOLS: a report's columns and filters may read ONE table of its record type as
``table.field``. Checker only, no bench: each refusal is planted into a passing manifest and must be
the only one. The install-time half (the shop's own record types) is in test_extension_package.py."""

import copy
import json
import pathlib
import unittest

import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from validate import validate  # noqa: E402

HERE = pathlib.Path(__file__).resolve().parent
OK = json.loads((HERE / "fixtures/report_cols_ok.json").read_text())
ONE_TABLE = "a column from a table is table.field, one table per report"


def planted(change):
    m = copy.deepcopy(OK)
    change(m)
    return validate(m)


def report(i, **k):
    return lambda m: m["reports"][i].update(k)


def second_table(m):
    """PP RPC Count gains a second table of its own rows' record type."""
    m["doctypes"][1]["fields"].append(
        {"fieldname": "more", "fieldtype": "Table", "label": "More", "options": "PP RPC Line"}
    )


def dashed(m):
    m["doctypes"][0]["name"] = "PP RPC Line-Row"
    m["doctypes"][1]["fields"][2]["options"] = "PP RPC Line-Row"


REFUSED = [
    ("two dots", report(0, columns=["items.qty.x"]), "columns is a list of field names"),
    ("two tables", report(0, columns=["items.qty", "taxes.rate"]), ONE_TABLE),
    ("a filter on a second table", report(0, filters=[["taxes.rate", ">", 0]]), ONE_TABLE),
    ("a filter with two dots", report(0, filters=[["items.qty.x", ">", 0]]), "filters are a list"),
    ("order_by on a table", report(0, order_by="items.qty"), "order_by is one field name"),
    (
        "own: not a table",
        report(1, columns=["title.note"], filters=[]),
        "title is not a table of PP RPC Count",
    ),
    (
        "own: no such row field",
        report(1, columns=["lines.nope"]),
        "nope is not a field of lines's rows",
    ),
    (
        "own: a document number beside the rows with a totals row",
        report(1, columns=["total", "lines.qty"]),
        "with a table's rows and a totals row, total of the document would be added once per line",
    ),
    ("own: two tables of the same rows", second_table, "would mix them"),
    ("own: rows whose record type carries a -", dashed, "a - in its name"),
]


class ReportColumns(unittest.TestCase):
    def test_the_fixture_passes(self):
        self.assertEqual(validate(OK), [])

    def test_without_a_totals_row_a_document_number_may_sit_beside_the_rows(self):
        self.assertEqual(planted(report(1, columns=["total", "lines.qty"], add_total_row=0)), [])

    def test_a_malformed_table_level_is_refused_not_raised(self):
        for level in ("x", [1]):
            with self.subTest(level=level):
                out = planted(lambda m: m["doctypes"][1]["fields"][2].update(permlevel=level))
                self.assertTrue(any("keys a field may not carry" in r["reason"] for r in out), out)

    def test_each_refusal_is_its_own(self):
        for label, change, phrase in REFUSED:
            with self.subTest(label):
                out = planted(change)
                self.assertEqual(len(out), 1, out)
                self.assertIn(phrase, out[0]["reason"])


if __name__ == "__main__":
    unittest.main()
