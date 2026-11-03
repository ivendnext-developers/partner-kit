"""S21's laptop tests: the manifest passes the kit's checker, every rule holds the published field-rules contract
(``fields.v1.schema.json`` in ``contracts/``, read by ``tools/contracts/check.py``), and the checker refuses,
in the product's own words, what the product would. Data only: no service. On our test bench the till's start read the
rules, the server refused a new customer without a phone, and uninstalling left the theme as it was.

    python3 -m unittest discover -s samples/s21_field_rules/tests -p 'test_*.py'
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


def row(r):
    """The theme row the installer appends (``apply._apply_waveb``): the rule without its theme."""
    return {k: v for k, v in r.items() if k != "theme"}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_relabel_hide_and_require_on_one_named_theme(self):
        self.assertEqual({r["theme"] for r in MANIFEST["field_rules"]}, {"PP Partner Till"})
        self.assertEqual(sorted(r["action"] for r in MANIFEST["field_rules"]), ["hide", "relabel", "relabel", "require"])
        self.assertIn({"theme": "PP Partner Till", "surface": "customer_create", "field": "phone", "action": "require"},
                      MANIFEST["field_rules"])


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_rule_holds_the_contract(self):
        for r in MANIFEST["field_rules"]:
            self.assertEqual(check.errors("fields", "rule", row(r)), [], r)

    def test_a_bad_rule_is_caught_by_the_contract(self):
        self.assertTrue(check.errors("fields", "rule", {"surface": "cart_line", "field": "qty", "action": "require"}))


if __name__ == "__main__":
    unittest.main()
