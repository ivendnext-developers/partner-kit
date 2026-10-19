"""S26's manifest: valid for the kit's checker; every rule field the service reads is declared; the app's user only reads
the rules; the feed registration follows Item Price; nothing the shop sends outside.

    python3 -m unittest discover -s samples/s26_derived_prices/tests -p 'test_*.py'
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

SAMPLE = Path(__file__).resolve().parent.parent
KIT = SAMPLE.parent.parent
M = json.loads((SAMPLE / "manifest.json").read_text())
[RULE] = M["doctypes"]
FIELDS = {f["fieldname"]: f for f in RULE["fields"]}


class Manifest(unittest.TestCase):
    def test_the_kits_checker_finds_it_valid(self):
        out = subprocess.run([sys.executable, str(KIT / "tools" / "manifest" / "validate.py"), str(SAMPLE / "manifest.json")],
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "VALID"), out.stdout + out.stderr)

    def test_every_rule_field_the_service_reads_is_declared(self):
        src = (SAMPLE / "prices.py").read_text()
        read = set(re.findall(r'raw(?:\.get\("|\[")(\w+)"', src)) - {"name"}
        self.assertEqual(read - set(FIELDS), set())
        self.assertEqual(len(read), 9)
        listed = set(re.findall(r'"(\w+)"', (SAMPLE / "sync.py").read_text().split("def rules")[1].split("def lists")[0]))
        self.assertEqual(listed - {"name"}, read)

    def test_the_choices_are_the_ones_the_rules_accept(self):
        import prices as P  # noqa: PLC0415
        self.assertEqual(tuple(FIELDS["rounding_step"]["options"].split("\n")), P.STEPS)
        self.assertEqual(FIELDS["rounding"]["options"].split("\n"), list(P.DIRECTIONS))

    def test_a_rule_is_named_by_its_short_name(self):
        self.assertEqual(RULE["autoname"], "field:rule_name")
        self.assertEqual((FIELDS["rule_name"].get("unique"), FIELDS["rule_name"].get("reqd")), (1, 1))

    def test_the_apps_user_only_reads_the_rules(self):
        perms = {p["role"]: {k for k, v in p.items() if v == 1} for p in RULE["permissions"]}
        self.assertEqual(perms["PP DPL Integration"], {"read"})

    def test_the_feed_follows_item_price_and_the_shop_calls_nothing_outside(self):
        self.assertEqual(M["registered_applications"][0]["events"], ["Item Price"])
        for k in ("extension_subscriptions", "remote_keys", "webhooks", "notifications", "allowed_urls"):
            self.assertFalse(M.get(k), k)

    def test_the_setup_and_what_leaves_are_in_the_description(self):
        for words in ("PP DPL Integration", "read, create and write on Item Price", "PP DPL Prices", "What leaves the shop",
                      "change any item price"):
            self.assertIn(words, M["description"])


sys.path.insert(0, str(SAMPLE))

if __name__ == "__main__":
    unittest.main()
