"""S32's manifest passes the kit's checker; the check installs switched off and lets the sale go on when down; the rule
record is one per coupon, readable by the integration role only, and opens its help."""
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
        self.assertEqual((sub["key"], sub["point"], sub["down_answer"]), ("coupons", "check", "allow_and_flag"))
        self.assertFalse(any(k in sub for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))

    def test_the_route_is_the_services_own_and_its_only_address(self):
        import app
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual("/" + sub["endpoint_url"].split("/", 3)[3], app.ROUTE)
        self.assertEqual(sub["key"], app.KEY)
        self.assertEqual(MANIFEST["allowed_urls"], [sub["endpoint_url"]])

    def test_one_rule_per_coupon_named_by_it_with_the_fields_the_service_reads(self):
        import coupons
        (dt,) = MANIFEST["doctypes"]
        self.assertEqual((dt["name"], dt["autoname"]), (MANIFEST["prefix"] + " Rule", "field:coupon"))
        fields = {f["fieldname"]: f for f in dt["fields"]}
        self.assertEqual((fields["coupon"]["options"], fields["coupon"]["unique"], fields["coupon"]["reqd"]), ("Coupon", 1, 1))
        self.assertEqual(fields["customer_group"]["options"], "Customer Group")
        self.assertEqual(set(coupons.RULE_FIELDS) - {"name"}, set(fields))

    def test_the_integration_role_only_reads_the_rules(self):
        (dt,) = MANIFEST["doctypes"]
        row = next(p for p in dt["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertEqual(row["role"], MANIFEST["prefix"] + " Integration")   # so the install makes it (the product's install rule)

    def test_the_rule_record_type_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (MANIFEST["prefix"] + " Rule", "documentation"))
        self.assertTrue(ps["value"].startswith("https://") and ps["value"].endswith("#rules"))


if __name__ == "__main__":
    unittest.main()
