"""S50's manifest passes the kit's checker; the check installs switched off and lets the sale go on when down; the rule
record is one per customer group with a table of sale details and one of POS Profiles, readable by the integration role
only, and opens its help."""
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

    def test_one_check_switched_off_that_lets_the_sale_go_on_when_down(self):
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual((sub["key"], sub["point"], sub["down_answer"], sub["timeout_seconds"]),
                         ("details", "check", "allow_and_flag", 3))
        self.assertFalse(any(k in sub for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))

    def test_the_route_is_the_services_own_and_its_only_address(self):
        import app
        (sub,) = MANIFEST["extension_subscriptions"]
        self.assertEqual("/" + sub["endpoint_url"].split("/", 3)[3], app.ROUTE)
        self.assertEqual(sub["key"], app.KEY)
        self.assertEqual(MANIFEST["allowed_urls"], [sub["endpoint_url"]])

    def test_one_rule_per_group_named_by_it_with_the_fields_the_service_reads(self):
        import details
        rule = TYPES[MANIFEST["prefix"] + " Rule"]
        self.assertEqual(rule["autoname"], "field:customer_group")
        fields = {f["fieldname"]: f for f in rule["fields"]}
        g = fields["customer_group"]
        self.assertEqual((g["options"], g["unique"], g["reqd"]), ("Customer Group", 1, 1))
        for name, table, link, target in (("details", " Rule Detail", "sale_attribute", "Sale Attribute"),
                                          ("profiles", " Rule Profile", "pos_profile", "POS Profile")):
            f = fields[name]
            self.assertEqual((f["fieldtype"], f["options"], f.get("reqd", 0)), ("Table", MANIFEST["prefix"] + table, 0))
            child = TYPES[MANIFEST["prefix"] + table]          # never reqd: no row is a rule's own meaning (none needed;
            self.assertEqual((child["istable"], [(c["fieldname"], c["options"]) for c in child["fields"]]),   # every till)
                             (1, [(link, target)]))
        read = {f.split(".")[0] for f in details.RULE_FIELDS} - {"name"}
        self.assertEqual(read, set(fields) - {"enabled"})
        self.assertEqual(details.RULE_FIELDS[-2:], ("details.sale_attribute", "profiles.pos_profile"))

    def test_the_words_fit_the_tills_sentence(self):
        rule = TYPES[MANIFEST["prefix"] + " Rule"]
        self.assertLessEqual(next(f for f in rule["fields"] if f["fieldname"] == "words")["length"], 140)

    def test_the_integration_role_only_reads_the_rules(self):
        rule = TYPES[MANIFEST["prefix"] + " Rule"]
        row = next(p for p in rule["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertEqual(row["role"], MANIFEST["prefix"] + " Integration")   # so the install makes it (the product's install rule)

    def test_the_feed_registration_fits_the_retailers_140_characters(self):
        (reg,) = MANIFEST["registered_applications"]
        self.assertLessEqual(len(reg["description"]), 140)

    def test_the_rule_record_type_opens_its_help(self):
        (ps,) = MANIFEST["property_setters"]
        self.assertEqual((ps["doc_type"], ps["property"]), (MANIFEST["prefix"] + " Rule", "documentation"))
        self.assertTrue(ps["value"].startswith("https://") and ps["value"].endswith("#rules"))


if __name__ == "__main__":
    unittest.main()
