"""Validator tests — the shape refusals: a manifest written wrongly rather than one asking for something forbidden. Each
case is planted into the good v1 manifest and is refused with its own named reason (row GAPS, 2026-10-08: these were
the 20 of the checker's 147 refusals that no test reached; the census is the programme's tools/kitcheck/refusal_census.py).

    python3 -m unittest discover -s tools/manifest/tests -v
"""

import copy
import json
import pathlib
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from validate import validate  # noqa: E402

FULL = json.loads((HERE / "fixtures/full_ok.json").read_text())


def planted(change):
    m = copy.deepcopy(FULL)
    change(m)
    return validate(m)


def fields(m):
    return m["doctypes"][1]["fields"]


# (label, change to FULL, a phrase the ONE refusal's reason must contain)
SHAPE = [
    ("a name with characters a name may not use", lambda m: m["print_formats"][0].update(name="PP TST <Card>"),
     "uses characters a name may not use"),
    ("a kind that is not a list", lambda m: m.update(sale_attributes={"name": "PP TST Reference"}),
     "'sale_attributes' must be a list of objects"),
    ("a field that is not an object", lambda m: fields(m).append("note"), "a field must be an object"),
    ("a field name with capitals and a space", lambda m: fields(m).append({"fieldname": "Bad Name", "fieldtype": "Data"}),
     "lower-case letters, digits and underscores"),
    ("an unknown field type", lambda m: fields(m).append({"fieldname": "rocket", "fieldtype": "Rocket"}),
     "'Rocket' is not a field type"),
    ("a table field pointing at a shop's record type", lambda m: fields(m).append(
        {"fieldname": "rows", "fieldtype": "Table", "options": "Customer"}), "the manifest's own child record types"),
    ("a record type key the checker does not know", lambda m: m["doctypes"][1].update(frobnicate=1),
     "keys a record type may not carry here: ['frobnicate']"),
    ("a record type with no fields", lambda m: m["doctypes"].append({"name": "PP TST Empty", "fields": []}),
     "needs at least one field"),
    ("a permission row with no role", lambda m: m["doctypes"][1].setdefault("permissions", []).append({"read": 1}),
     "a permission row needs a role"),
    ("a custom field naming no record type", lambda m: m["custom_fields"].append(
        {"fieldname": "pp_tst_x", "fieldtype": "Data"}), "must name the record type it is added to"),
    ("a property setter with no value", lambda m: m["property_setters"].append(
        {"doc_type": "PP TST Record", "field_name": "title", "property": "bold"}), "needs doc_type, property and value"),
    ("a print format naming no record type", lambda m: m["print_formats"][0].pop("doc_type"),
     "a print format must name its record type"),
    ("a notification on an event it may not use", lambda m: m["notifications"][0].update(event="Every Minute"),
     "'Every Minute' is not an event"),
    ("a workspace block of an unknown type", lambda m: m["workspaces"][0]["blocks"].append({"type": "iframe", "data": {}}),
     "'iframe' is not a workspace block"),
    ("a shortcut with no target", lambda m: m["workspaces"][0]["shortcuts"].append({"type": "DocType", "label": "X"}),
     "a shortcut needs a label, a type"),
    ("a webhook naming no event", lambda m: m["webhooks"][0].pop("event"), "must name its record type and event"),
    ("a webhook key it may not carry", lambda m: m["webhooks"][0].update(headers={"X-Partner": "1"}),
     "keys a webhook may not carry: ['headers']"),
    ("a manifest version this installer does not read", lambda m: m.update(manifest_version=3),
     "reads manifest_version 1 or 2"),
    ("an address that is not plain http(s)", lambda m: m["allowed_urls"].append("ftp://partner.example/x"),
     "allowed_urls is a list of plain http(s) addresses"),
]


class Shape(unittest.TestCase):
    def test_each_shape_mistake_is_refused_with_its_reason(self):
        for label, change, phrase in SHAPE:
            with self.subTest(label):
                refusals = planted(change)
                self.assertEqual(len(refusals), 1, f"{label}: {refusals}")
                self.assertIn(phrase, refusals[0]["reason"], f"{label}: {refusals[0]}")

    def test_a_lower_case_prefix_is_refused(self):
        # every name then misses the prefix too, so this one is refused among others, by its own reason
        refusals = planted(lambda m: m.update(prefix="pp tst"))
        self.assertIn("the prefix is one to three upper-case words", [r["reason"] for r in refusals][0])
        self.assertEqual(refusals[0]["where"], "prefix")

    def test_a_manifest_that_is_not_an_object_is_refused(self):
        self.assertEqual(validate([]), [{"where": "", "name": None, "reason": "a manifest is a JSON object"}])


if __name__ == "__main__":
    unittest.main()
