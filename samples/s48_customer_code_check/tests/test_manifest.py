"""S48's manifest passes the kit's checker; the capture on customer select installs switched off and keeps the customer
on the sale when down; the rule record is one per customer group, readable by the integration role only; the code record
is named by the till's code-check id, holds what the shop's Notification texts, and is the integration role's alone; both
open their help."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
TYPES = {d["name"]: d for d in MANIFEST["doctypes"]}
P = MANIFEST["prefix"]


def fields(dt):
    return {f["fieldname"]: f for f in TYPES[dt]["fields"]}


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
        import codecheck
        rule = TYPES[P + " Rule"]
        self.assertEqual(rule["autoname"], "field:customer_group")
        f = fields(P + " Rule")
        g = f["customer_group"]
        self.assertEqual((g["options"], g["unique"], g["reqd"]), ("Customer Group", 1, 1))
        self.assertEqual(f["ask"]["options"].split("\n"), [codecheck.ASK, codecheck.NEVER])
        self.assertEqual(f["ask"]["default"], codecheck.ASK)
        self.assertEqual(f["without_mobile"]["options"].split("\n"), [codecheck.TAKE_OFF, codecheck.LET_ON])
        self.assertEqual(f["without_mobile"]["default"], codecheck.TAKE_OFF)
        self.assertEqual(set(codecheck.RULE_FIELDS) - {"name"}, set(f) - {"enabled"})

    def test_the_code_record_is_named_by_the_code_check_and_holds_what_the_notification_and_the_service_read(self):
        import codecheck
        code = TYPES[P + " Code"]
        self.assertEqual(code["autoname"], "field:challenge")
        f = fields(P + " Code")
        self.assertEqual((f["challenge"]["unique"], f["challenge"]["reqd"]), (1, 1))
        self.assertEqual((f["customer"]["fieldtype"], f["customer"]["options"]), ("Link", "Customer"))
        self.assertEqual((f["mobile"]["fieldtype"], f["mobile"]["options"]), ("Data", "Phone"))
        self.assertEqual(f["status"]["options"].split("\n"), [codecheck.SENT, codecheck.USED])
        self.assertEqual((f["sent_at"]["fieldtype"], f["verified_at"]["fieldtype"]), ("Int", "Int"))
        import test_rules
        written = codecheck.code_record(test_rules.context(), "123456", 1)
        self.assertEqual(set(written) | {"verified_at"}, set(f))                     # every field the service writes exists
        self.assertTrue(set(codecheck.CODE_FIELDS) - {"name"} <= set(f))
        self.assertGreaterEqual(f["code"]["length"], codecheck.LENGTH)

    def test_the_words_fit_the_tills_sentence(self):
        self.assertLessEqual(fields(P + " Rule")["words"]["length"], 140)

    def test_the_integration_role_only_reads_the_rules(self):
        row = next(p for p in TYPES[P + " Rule"]["permissions"] if p["role"] != "System Manager")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read"})
        self.assertEqual(row["role"], P + " Integration")   # so the install makes it (the product's install rule)

    def test_the_code_records_are_the_integration_roles_alone(self):
        (row,) = TYPES[P + " Code"]["permissions"]          # no other role reads a code
        self.assertEqual(row["role"], P + " Integration")
        self.assertEqual({k for k, v in row.items() if k != "role" and v}, {"read", "write", "create"})

    def test_the_feed_registration_fits_the_shops_140_characters(self):
        (reg,) = MANIFEST["registered_applications"]
        self.assertLessEqual(len(reg["description"]), 140)

    def test_both_record_types_open_their_help(self):
        got = {(ps["doc_type"], ps["property"]): ps["value"] for ps in MANIFEST["property_setters"]}
        self.assertTrue(got[(P + " Rule", "documentation")].endswith("#rules"))
        self.assertTrue(got[(P + " Code", "documentation")].endswith("#the-text-message"))


if __name__ == "__main__":
    unittest.main()
