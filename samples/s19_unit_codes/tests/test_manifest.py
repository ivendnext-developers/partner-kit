"""S19's laptop tests: the manifest passes the kit's checker, and the scan source it installs — the record the installer
inserts, switched off — holds the published scan-source contract (``scan_source.v1.schema.json`` at the POS app's pinned
commit, read by ``tools/contracts/check.py``). Data only: there is no service to test. On our test bench the till's own
scan found a unit, refused a sold one and put its code on the line.

    python3 -m unittest discover -s samples/s19_unit_codes/tests -p 'test_*.py'
"""
import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "tools" / "manifest"), str(ROOT / "tools" / "contracts")]
import check  # noqa: E402
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())


def installed(src: dict) -> dict:
    """The record the installer inserts (``apply._apply_waveb``): the statuses one per line, switched off."""
    return {"doctype": "Retail Scan Source", **{k: v for k, v in src.items() if k != "available_values"},
            "available_values": "\n".join(src.get("available_values") or []), "enabled": 0}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_the_unit_table_names_one_unit_by_one_code(self):
        unit = MANIFEST["doctypes"][0]
        fields = {f["fieldname"]: f for f in unit["fields"]}
        src = MANIFEST["scan_sources"][0]
        self.assertEqual(src["record_type"], unit["name"])
        self.assertTrue(fields[src["barcode_field"]]["unique"])
        self.assertEqual((fields["item"]["options"], fields["batch"]["options"]), ("Item", "Batch"))
        self.assertEqual(fields["status"]["options"].split("\n"), ["Available", "Sold"])
        self.assertEqual(src["available_values"], ["Available"])

    def test_the_source_is_not_switched_on_by_the_manifest(self):
        self.assertNotIn("enabled", MANIFEST["scan_sources"][0])
        self.assertNotIn("capture_as", MANIFEST["scan_sources"][0])      # the shop's own line attribute, set by the shop

    def test_the_checker_refuses_what_the_product_would(self):
        for change, words in ((lambda s: s.pop("status_field") and s.update(capture_as="Unit code"), "Recording the code needs"),
                              (lambda s: s.update(enabled=1), "switches it on")):
            m = copy.deepcopy(MANIFEST)
            change(m["scan_sources"][0])
            self.assertTrue(any(words in r["reason"] for r in validate.validate(m)), validate.validate(m))
        m = copy.deepcopy(MANIFEST)
        m["doctypes"][0]["fields"][0]["unique"] = 0
        self.assertTrue(any("unique" in r["reason"] for r in validate.validate(m)))


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_installed_source_holds_the_contract(self):
        self.assertEqual(check.errors("scan_source", "declaration", installed(MANIFEST["scan_sources"][0])), [])

    def test_with_the_shops_line_attribute_it_still_holds(self):
        src = installed({**MANIFEST["scan_sources"][0], "capture_as": "Unit code"})
        self.assertEqual(check.errors("scan_source", "declaration", src), [])

    def test_a_bad_source_is_caught_by_the_contract(self):
        bad = installed(MANIFEST["scan_sources"][0])
        bad.pop("status_field")
        bad["capture_as"] = "Unit code"
        self.assertTrue(check.errors("scan_source", "declaration", bad))      # the checker is live


if __name__ == "__main__":
    unittest.main()
