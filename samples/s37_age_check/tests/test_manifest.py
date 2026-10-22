"""S37's manifest passes the kit's checker; both services install switched off and let the item or the sale go on when
down; the scan's filter is the app's own age field; the fields, the sale detail and the settings are the ones the service
reads; the integration role only reads the settings, and the settings open their help."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
SUBS = {s["key"]: s for s in MANIFEST["extension_subscriptions"]}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_two_services_switched_off_that_let_the_sale_go_on_when_down(self):
        self.assertEqual({k: (s["point"], s["down_answer"]) for k, s in SUBS.items()},
                         {"scan": ("capture", "allow_and_flag"), "check": ("check", "allow_and_flag")})
        for s in SUBS.values():
            self.assertFalse(any(k in s for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))
        self.assertLessEqual(SUBS["scan"]["timeout_seconds"], 3)
        self.assertLessEqual(SUBS["check"]["timeout_seconds"], 10)

    def test_the_scan_asks_about_the_items_the_app_gives_an_age(self):
        self.assertEqual(SUBS["scan"]["settings"], {"event": "scan", "item_field": f"{MANIFEST['app']}_min_age"})

    def test_the_routes_are_the_services_own_and_its_only_addresses(self):
        import app
        for key, s in SUBS.items():
            path = "/" + s["endpoint_url"].split("/", 3)[3]
            self.assertEqual(app.ROUTES[path][0], key)
        self.assertEqual(sorted(MANIFEST["allowed_urls"]), sorted(s["endpoint_url"] for s in SUBS.values()))
        self.assertEqual(len({u.split("/")[2] for u in MANIFEST["allowed_urls"]}), 1)   # one origin

    def test_the_sale_detail_is_the_check_the_service_reads_and_is_never_required(self):
        import agecheck
        (sa,) = MANIFEST["sale_attributes"]
        self.assertEqual(sa, {"name": f"{MANIFEST['prefix']} {agecheck.CHECKED}"})

    def test_the_fields_are_the_ones_the_service_reads(self):
        p = MANIFEST["app"]
        got = {(f["dt"], f["fieldname"], f["fieldtype"]) for f in MANIFEST["custom_fields"]}
        self.assertEqual(got, {("Item Group", f"{p}_min_age", "Int"), ("Item", f"{p}_min_age", "Int")})

    def test_the_settings_record_holds_what_the_service_reads(self):
        (dt,) = MANIFEST["doctypes"]
        self.assertEqual((dt["name"], dt["autoname"]), (MANIFEST["prefix"] + " Settings", "field:title"))
        self.assertEqual({f["fieldname"] for f in dt["fields"]}, {"title", "hours_from_utc", "look_under"})

    def test_the_integration_role_only_reads_the_settings(self):
        (dt,) = MANIFEST["doctypes"]
        row = next(p for p in dt["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertEqual(row["role"], MANIFEST["prefix"] + " Integration")   # so the install makes it (the product's install rule)

    def test_the_settings_open_their_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (MANIFEST["prefix"] + " Settings", "documentation"))
        self.assertTrue(ps["value"].startswith("https://") and ps["value"].endswith("#settings"))


if __name__ == "__main__":
    unittest.main()
