"""S47's manifest passes the kit's checker; the capture on customer select installs switched off and keeps the customer
on the sale when down; the rule record is one per customer group with a table of places, readable by the integration
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


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_one_select_capture_switched_off_that_keeps_the_customer_on_when_down(self):
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual((sub["key"], sub["point"], sub["down_answer"], sub["timeout_seconds"], sub["settings"]),
                         ("on_select", "capture", "allow_and_flag", 3, {"event": "customer_select"}))
        self.assertFalse(any(k in sub for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))

    def test_the_route_is_the_services_own_and_its_only_address(self):
        import app
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual("/" + sub["endpoint_url"].split("/", 3)[3], app.ROUTE)
        self.assertEqual(sub["key"], app.KEY)
        self.assertEqual(MANIFEST["allowed_urls"], [sub["endpoint_url"]])

    def test_one_rule_per_group_named_by_it_with_the_fields_the_service_reads(self):
        import storerules
        rule = TYPES[MANIFEST["prefix"] + " Rule"]
        self.assertEqual(rule["autoname"], "field:customer_group")
        fields = {f["fieldname"]: f for f in rule["fields"]}
        g = fields["customer_group"]
        self.assertEqual((g["options"], g["unique"], g["reqd"]), ("Customer Group", 1, 1))
        self.assertEqual((fields["places"]["fieldtype"], fields["places"]["options"], fields["places"]["reqd"]),
                         ("Table", MANIFEST["prefix"] + " Rule Place", 1))
        table = TYPES[MANIFEST["prefix"] + " Rule Place"]
        self.assertEqual((table["istable"], [(f["fieldname"], f["options"]) for f in table["fields"]]),
                         (1, [("store", "Warehouse"), ("pos_profile", "POS Profile")]))
        self.assertFalse(any(f.get("reqd") for f in table["fields"]))          # a row fills a store, a POS Profile or both
        read = {f.split(".")[0] for f in storerules.RULE_FIELDS} - {"name"}
        self.assertEqual(read, set(fields) - {"enabled"})
        self.assertEqual(storerules.RULE_FIELDS[-2:], ("places.store", "places.pos_profile"))

    def test_the_words_fit_the_tills_sentence(self):
        rule = TYPES[MANIFEST["prefix"] + " Rule"]
        self.assertLessEqual(next(f for f in rule["fields"] if f["fieldname"] == "words")["length"], 140)

    def test_the_integration_role_only_reads_the_rules(self):
        rule = TYPES[MANIFEST["prefix"] + " Rule"]
        row = next(p for p in rule["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertEqual(row["role"], MANIFEST["prefix"] + " Integration")   # so the install makes it (the product's install rule)

    def test_the_feed_registration_fits_the_shops_140_characters(self):
        (reg,) = MANIFEST["registered_applications"]
        self.assertLessEqual(len(reg["description"]), 140)

    def test_the_rule_record_type_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (MANIFEST["prefix"] + " Rule", "documentation"))
        self.assertTrue(ps["value"].startswith("https://") and ps["value"].endswith("#rules"))


if __name__ == "__main__":
    unittest.main()
