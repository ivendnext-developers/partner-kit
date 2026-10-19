"""S27's manifest: valid for the kit's checker; every alert field the service writes and every settings field it reads
is declared; the notification is on the app's own alert, to the app's role and the user the settings name; the app's
user writes alerts and reads the settings, nothing more; nothing the shop sends outside.

    python3 -m unittest discover -s samples/s27_stock_alerts/tests -p 'test_*.py'
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
T = {d["name"]: d for d in M["doctypes"]}
FIELDS = {n: {f["fieldname"]: f for f in d["fields"]} for n, d in T.items()}
RUN = (SAMPLE / "run.py").read_text()


class Manifest(unittest.TestCase):
    def test_the_kits_checker_finds_it_valid(self):
        out = subprocess.run([sys.executable, str(KIT / "tools" / "manifest" / "validate.py"), str(SAMPLE / "manifest.json")],
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "VALID"), out.stdout + out.stderr)

    def test_every_alert_field_the_service_writes_is_declared(self):
        block = RUN.split("doc = {\"alert_key\"")[1].split("}")[0]
        written = {"alert_key", *re.findall(r'"(\w+)": ', block)}
        self.assertEqual(written - set(FIELDS["PP STK Alert"]), set())
        self.assertEqual(len(written), 12)

    def test_every_settings_field_the_rules_read_is_declared(self):
        src = (SAMPLE / "alerts.py").read_text() + RUN
        read = set(re.findall(r'\b(?:st|settings)\.get\("(\w+)"\)', src))
        self.assertEqual(read - set(FIELDS["PP STK Settings"]), set())
        self.assertGreaterEqual(read, {"enabled", "source_warehouse", "clearance_warehouse", "expiry_days", "notify_user", "stores"})

    def test_an_alert_is_named_by_its_key(self):
        self.assertEqual(T["PP STK Alert"]["autoname"], "field:alert_key")
        f = FIELDS["PP STK Alert"]["alert_key"]
        self.assertEqual((f.get("unique"), f.get("reqd")), (1, 1))

    def test_the_rights(self):
        perms = {(d, p["role"]): {k for k, v in p.items() if v == 1} for d, t in T.items() for p in t["permissions"]}
        self.assertEqual(perms[("PP STK Alert", "PP STK Integration")], {"read", "write", "create"})
        self.assertEqual(perms[("PP STK Settings", "PP STK Integration")], {"read"})
        self.assertNotIn("write", perms[("PP STK Alert", "PP STK Alerts")])

    def test_the_notification_is_on_the_apps_own_alert_to_its_own_people(self):
        [n] = M["notifications"]
        self.assertEqual((n["document_type"], n["event"], n["channel"]), ("PP STK Alert", "New", "System Notification"))
        self.assertEqual(n["recipients"], [{"receiver_by_role": "PP STK Alerts"}, {"receiver_by_document_field": "notify_user"}])
        self.assertEqual(FIELDS["PP STK Alert"]["notify_user"]["options"], "User")

    def test_the_shop_calls_nothing_outside(self):
        for k in ("extension_subscriptions", "remote_keys", "webhooks", "allowed_urls", "registered_applications"):
            self.assertFalse(M.get(k), k)

    def test_the_setup_and_what_leaves_are_in_the_description(self):
        for words in ("PP STK Integration", "read, create and write on Material Request", "Serial and Batch Bundle",
                      "PP STK Settings Default", "What leaves the shop", "never submits"):
            self.assertIn(words, M["description"])


if __name__ == "__main__":
    unittest.main()
