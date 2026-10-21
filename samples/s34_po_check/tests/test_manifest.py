"""S34's manifest: the kit's checker (the shop's install screen runs the same) takes it, and it says what the service needs."""

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools" / "manifest"))
from validate import validate  # noqa: E402

M = json.loads((HERE.parent / "manifest.json").read_text())


class ManifestTest(unittest.TestCase):
    def test_the_checker_takes_it(self):
        self.assertEqual(validate(M), [])

    def test_the_check_fills_only_the_field_the_manifest_adds(self):
        sub = M["extension_subscriptions"][0]
        added = {(f["dt"], f["fieldname"]) for f in M["custom_fields"]}
        self.assertEqual(sub["point"], "doccheck")
        self.assertEqual([("Purchase Order", f) for f in sub["settings"]["fill_fields"]], sorted(added))
        self.assertEqual(sub["settings"]["record_type"], "Purchase Order")

    def test_nothing_is_submitted_unchecked_and_the_address_is_listed(self):
        sub = M["extension_subscriptions"][0]
        self.assertEqual((sub["down_answer"], sub["settings"]["on_validate"]), ("refuse", False))
        self.assertIn(sub["endpoint_url"], M["allowed_urls"])

    def test_a_check_switched_on_by_the_manifest_is_refused(self):
        on = json.loads(json.dumps(M))
        on["extension_subscriptions"][0]["enabled"] = 1
        self.assertTrue(validate(on))


if __name__ == "__main__":
    unittest.main()
