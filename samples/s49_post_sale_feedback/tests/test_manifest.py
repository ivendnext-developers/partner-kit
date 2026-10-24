"""S49's manifest: a rule with its POS Profiles, one request per sale named by it, one button on the rule for the app's
manager sending no more than the rule's name, the requests written by the app's role alone, a report of the answers,
and the address the service's.

    python3 -m unittest discover -s samples/s49_post_sale_feedback/tests -p 'test_*.py'
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
MANIFEST = os.path.join(SAMPLE, "manifest.json")
sys.path.insert(0, SAMPLE)
import feedback as fb  # noqa: E402


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.types = {d["name"]: d for d in self.m["doctypes"]}
        self.rule = {f["fieldname"]: f for f in self.types["PP PSF Rule"]["fields"]}
        self.req = {f["fieldname"]: f for f in self.types["PP PSF Request"]["fields"]}

    def test_three_record_types_one_a_table(self):
        self.assertEqual(sorted(self.types), ["PP PSF Request", "PP PSF Rule", "PP PSF Rule Profile"])
        self.assertEqual(self.rule["profiles"]["options"], "PP PSF Rule Profile")
        self.assertFalse(self.rule["profiles"].get("reqd"))          # none: every POS Profile (Desk drops a blank row)

    def test_the_rules_fields_are_the_ones_the_service_reads(self):
        read = {f.split(".")[0] for f in __import__("app").RULE_FIELDS} - {"name"}
        self.assertEqual(read, set(self.rule) - {"rule_name"})
        self.assertFalse(self.rule["asked_up_to"].get("read_only"))      # a manager may clear it to read the days again
        self.assertEqual((self.rule["question"]["default"], self.rule["answer_good"]["default"],
                          self.rule["answer_ok"]["default"], self.rule["answer_bad"]["default"]),
                         (fb.DEFAULT_QUESTION, *fb.ANSWERS))

    def test_a_request_is_named_by_its_sale_and_holds_what_the_service_writes(self):
        self.assertEqual(self.types["PP PSF Request"]["autoname"], "field:sale")
        written = set(fb.request_of({"name": "S", "customer": "C", "posting_date": "2026-10-24"},
                                    fb.rule_of({"name": "R", "enabled": 1, "shown_name": "x"}), "", "", "", ""))
        self.assertLessEqual(written | {"answer", "comment", "answered_at", "asked_to_stop"}, set(self.req))
        self.assertTrue(all(f.get("read_only") for f in self.req.values()))
        self.assertEqual(self.req["answer"]["options"].split("\n"), ["", *fb.ANSWERS])
        self.assertEqual((self.req["mobile"]["options"], self.req["email"]["options"]), ("Phone", "Email"))
        self.assertFalse(self.req["asked_to_stop"].get("in_standard_filter"))   # a Check is never a standard filter

    def test_the_apps_role_alone_writes_requests_and_the_manager_reads_them(self):
        perms = {p["role"]: p for p in self.types["PP PSF Request"]["permissions"]}
        self.assertEqual(sorted(k for k, v in perms["PP PSF Integration"].items() if v == 1), ["create", "read", "write"])
        self.assertEqual(sorted(k for k, v in perms["PP PSF Manager"].items() if v == 1), ["export", "read", "report"])
        rule = {p["role"]: p for p in self.types["PP PSF Rule"]["permissions"]}
        self.assertEqual(sorted(k for k, v in rule["PP PSF Integration"].items() if v == 1), ["read", "write"])

    def test_the_button_is_on_the_rule_for_its_manager_and_sends_only_its_name(self):
        (a,) = self.m["desk_actions"]
        self.assertEqual((a["record_type"], a["label"], a["placement"], a["service"], a["roles"], a["send_fields"]),
                         ("PP PSF Rule", "Send feedback requests", "both", "send", ["PP PSF Manager"], "name"))
        self.assertLessEqual(len(a["confirm_text"]), 140)
        (s,) = self.m["extension_subscriptions"]
        self.assertEqual((s["key"], s["point"], s["timeout_seconds"]), ("send", "desk_action", 10))
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"]])

    def test_the_report_lists_answered_requests(self):
        (r,) = self.m["reports"]
        self.assertEqual((r["ref_doctype"], r["filters"]), ("PP PSF Request", [["status", "=", "Answered"]]))
        self.assertTrue(set(r["columns"]) <= set(self.req))

    def test_the_feed_registration_fits(self):
        (f,) = self.m["registered_applications"]
        self.assertLessEqual(len(f["description"]), 140)


if __name__ == "__main__":
    unittest.main()
