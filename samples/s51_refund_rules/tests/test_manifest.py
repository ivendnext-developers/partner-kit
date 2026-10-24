"""S51's manifest passes the kit's checker; the check installs switched off and lets the refund go on when down; the settings
record is named Default with the fields the service reads and two tables of payment methods, readable by the integration
role only, and opens its help."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
TYPES = {d["name"]: d for d in MANIFEST["doctypes"]}
SETTINGS = TYPES[MANIFEST["prefix"] + " Settings"]
FIELDS = {f["fieldname"]: f for f in SETTINGS["fields"]}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_one_check_switched_off_that_lets_the_refund_go_on_when_down(self):
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual((sub["key"], sub["point"], sub["down_answer"], sub["timeout_seconds"]),
                         ("refunds", "check", "allow_and_flag", 3))
        self.assertFalse(any(k in sub for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))

    def test_the_route_is_the_services_own_and_its_only_address(self):
        import app
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual("/" + sub["endpoint_url"].split("/", 3)[3], app.ROUTE)
        self.assertEqual(sub["key"], app.KEY)
        self.assertEqual(MANIFEST["allowed_urls"], [sub["endpoint_url"]])

    def test_the_settings_record_is_named_default_with_the_fields_the_service_reads(self):
        import refunds
        self.assertEqual(SETTINGS["autoname"], "field:title")
        self.assertEqual((FIELDS["title"]["default"], FIELDS["title"]["unique"]), ("Default", 1))
        self.assertEqual(FIELDS["same_methods"]["fieldtype"], "Check")
        self.assertEqual(FIELDS["same_methods"].get("default"), "0")                 # every rule off until the retailer sets it
        self.assertEqual((FIELDS["store_credit"]["options"], FIELDS["store_credit"]["mandatory_depends_on"]),
                         ("Mode of Payment", "same_methods"))
        doc = {"same_methods": 1, "store_credit": "SC", "always_allowed": [{"mode_of_payment": "A"}],
               "without_sale": [{"mode_of_payment": "B"}]}
        self.assertEqual(set(doc), set(FIELDS) - {"title"})                           # the service reads every field
        self.assertEqual(refunds.settings_of(doc), {"same_methods": True, "store_credit": "SC", "always": ["A"],
                                                    "without_sale": ["B"]})

    def test_both_tables_are_payment_methods_never_required(self):
        child = TYPES[MANIFEST["prefix"] + " Method"]
        self.assertEqual((child["istable"], [(c["fieldname"], c["options"]) for c in child["fields"]]),
                         (1, [("mode_of_payment", "Mode of Payment")]))
        for name in ("always_allowed", "without_sale"):
            f = FIELDS[name]
            self.assertEqual((f["fieldtype"], f["options"], f.get("reqd", 0)), ("Table", MANIFEST["prefix"] + " Method", 0))

    def test_the_integration_role_only_reads_the_settings(self):
        row = next(p for p in SETTINGS["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertEqual(row["role"], MANIFEST["prefix"] + " Integration")   # so the install makes it (the product's install rule)

    def test_the_feed_registration_fits_the_retailers_140_characters(self):
        (reg,) = MANIFEST["registered_applications"]
        self.assertLessEqual(len(reg["description"]), 140)

    def test_the_settings_record_type_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (MANIFEST["prefix"] + " Settings", "documentation"))
        self.assertTrue(ps["value"].startswith("https://") and ps["value"].endswith("#settings"))


if __name__ == "__main__":
    unittest.main()
