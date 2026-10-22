"""S36's manifest passes the kit's checker; the check installs switched off and lets the sale go on when down; the fields,
the sale detail and the settings are the ones the service reads; the integration role only reads the settings, and the
settings open their help."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_one_check_switched_off_that_lets_the_sale_go_on_when_down(self):
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual((sub["key"], sub["point"], sub["down_answer"]), ("allowance", "check", "allow_and_flag"))
        self.assertFalse(any(k in sub for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))
        self.assertLessEqual(sub["timeout_seconds"], 10)

    def test_the_route_is_the_services_own_and_its_only_address(self):
        import app
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual("/" + sub["endpoint_url"].split("/", 3)[3], app.ROUTE)
        self.assertEqual(sub["key"], app.KEY)
        self.assertEqual(MANIFEST["allowed_urls"], [sub["endpoint_url"]])

    def test_the_sale_detail_is_the_pass_the_service_reads_and_is_never_required(self):
        import dutyfree
        (sa,) = MANIFEST["sale_attributes"]
        self.assertEqual(sa, {"name": f"{MANIFEST['prefix']} {dutyfree.PASS}"})

    def test_the_fields_are_the_ones_the_service_reads(self):
        p = MANIFEST["app"]
        got = {(f["dt"], f["fieldname"], f["fieldtype"]) for f in MANIFEST["custom_fields"]}
        self.assertEqual(got, {("Item Group", f"{p}_allowance", "Float"), ("Item Group", f"{p}_unit", "Data"),
                               ("Item", f"{p}_counts_as", "Float")})

    def test_the_settings_record_holds_what_the_service_reads(self):
        import dutyfree
        (dt,) = MANIFEST["doctypes"]
        self.assertEqual((dt["name"], dt["autoname"]), (MANIFEST["prefix"] + " Settings", "field:title"))
        fields = {f["fieldname"]: f for f in dt["fields"]}
        self.assertEqual(set(dutyfree.SETTINGS_FIELDS) | {"title"}, set(fields))
        self.assertEqual(fields["direction"]["options"].split("\n"), ["departing", "arriving"])
        self.assertEqual(fields["count_earlier_sales"]["default"], "1")

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
