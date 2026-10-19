"""S23's manifest passes the kit's checker; both services install switched off and let the sale go on when down; the
scan service is filtered by the item's own tick; the settings record is readable by the integration role only."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service")]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_two_services_switched_off_that_let_the_sale_go_on_when_down(self):
        subs = {s["key"]: s for s in MANIFEST["extension_subscriptions"]}
        self.assertEqual(sorted(subs), ["guard", "on_scan"])
        self.assertEqual((subs["guard"]["point"], subs["on_scan"]["point"]), ("check", "capture"))
        for s in subs.values():
            self.assertEqual(s["down_answer"], "allow_and_flag")
            self.assertFalse(any(k in s for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))

    def test_the_scan_asks_only_about_items_the_shop_ticked(self):
        (field,) = MANIFEST["custom_fields"]
        scan = next(s for s in MANIFEST["extension_subscriptions"] if s["key"] == "on_scan")
        self.assertEqual(scan["settings"], {"event": "scan", "item_field": field["fieldname"]})
        self.assertEqual((field["dt"], field["fieldtype"]), ("Item", "Check"))

    def test_the_routes_are_the_services_own(self):
        import app
        for s in MANIFEST["extension_subscriptions"]:
            path = "/" + s["endpoint_url"].split("/", 3)[3]
            self.assertEqual(app.ROUTES[path][0], s["key"])
            self.assertIn(s["endpoint_url"], MANIFEST["allowed_urls"])

    def test_the_integration_role_only_reads_the_settings(self):
        (dt,) = MANIFEST["doctypes"]
        self.assertEqual(dt["name"], MANIFEST["prefix"] + " Settings")
        row = next(p for p in dt["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertTrue(row["role"].startswith(MANIFEST["prefix"] + " "))   # so the install makes it (the product's install rule)

    def test_the_settings_record_type_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (MANIFEST["prefix"] + " Settings", "documentation"))
        self.assertTrue(ps["value"].startswith("https://"))


if __name__ == "__main__":
    unittest.main()
