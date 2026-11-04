"""S18's manifest passes the kit's checker: one check, on from the install, with the product's own answer when its service is down."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2] / "tools" / "manifest"))
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_one_check_that_leaves_the_down_answer_to_the_shop(self):
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual(sub["point"], "check")
        self.assertNotIn("down_answer", sub)
        self.assertFalse(any(k in sub for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))


if __name__ == "__main__":
    unittest.main()
