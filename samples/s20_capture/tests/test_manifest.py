"""S20's manifest passes the kit's checker: three capture services, one per event, installed switched off."""
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

    def test_one_service_per_event_none_switched_on(self):
        subs = MANIFEST["extension_subscriptions"]
        self.assertEqual(sorted(s["settings"]["event"] for s in subs), ["customer_add", "qty_change", "scan"])
        self.assertFalse(any(k in s for s in subs for k in ("enabled", "consent_given", "scope", "secret")))
        by = {s["settings"]["event"]: s for s in subs}
        self.assertLessEqual(by["scan"]["timeout_seconds"], 3)
        self.assertLessEqual(by["qty_change"]["timeout_seconds"], 3)
        self.assertLessEqual(set(by["qty_change"]["settings"]["item_groups"]), set(by["scan"]["settings"]["item_groups"]))


if __name__ == "__main__":
    unittest.main()
