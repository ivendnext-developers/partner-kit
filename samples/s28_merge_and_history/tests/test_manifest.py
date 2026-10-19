"""S28's manifest: valid for the kit's checker; one prefix for both doors; the button admits drafts only and sends only
the names; the page asks for the sale and never the user; every settings field the service reads is declared.

    python3 -m unittest discover -s samples/s28_merge_and_history/tests -p 'test_*.py'
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
SUBS = {s["key"]: s for s in M["extension_subscriptions"]}


class Manifest(unittest.TestCase):
    def test_the_kits_checker_finds_it_valid(self):
        out = subprocess.run([sys.executable, str(KIT / "tools" / "manifest" / "validate.py"), str(SAMPLE / "manifest.json")],
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "VALID"), out.stdout + out.stderr)

    def test_one_prefix_for_both_doors(self):
        self.assertEqual((M["app"], M["prefix"]), ("pp_mhs", "PP MHS"))
        roles = {p["role"] for d in M["doctypes"] for p in d["permissions"]} | set(SUBS["history"]["page_roles"]) \
            | {r for a in M["desk_actions"] for r in a["roles"]}
        self.assertEqual({r for r in roles if r != "System Manager"}, {"PP MHS Integration", "PP MHS Counts", "PP MHS History"})

    def test_the_button_admits_drafts_only_from_the_list_and_sends_only_names(self):
        (a,) = M["desk_actions"]
        self.assertEqual((a["record_type"], a["placement"], a["on_draft"], a["on_submitted"], a["send_fields"], a["service"]),
                         ("Stock Reconciliation", "list", 1, 0, "name", "merge"))

    def test_the_page_asks_for_the_sale_never_the_user_and_answers_nothing_but_what_it_must(self):
        p = SUBS["history"]
        self.assertEqual((p["point"], p["page_send_sale"], p["page_send_user"], p["page_returns_sale_attributes"]),
                         ("page", 1, 0, 0))

    def test_the_press_key_field_is_the_one_the_core_writes(self):
        sys.path.insert(0, str(SAMPLE))
        import merge
        (f,) = M["custom_fields"]
        self.assertEqual((f["dt"], f["fieldname"]), (merge.COUNT, merge.KEY_FIELD))

    def test_every_settings_field_the_service_reads_is_declared(self):
        src = (SAMPLE / "service" / "app.py").read_text() + (SAMPLE / "history.py").read_text()
        read = set(re.findall(r'settings\.result\(\)\.get\("(\w+)"\)|\(settings or \{\}\)\.get\("(\w+)"\)', src))
        read = {a or b for a, b in read}
        declared = {f["fieldname"] for f in M["doctypes"][0]["fields"]}
        self.assertEqual(read, {"merge_rule", "history_count"})
        self.assertLessEqual(read, declared)


if __name__ == "__main__":
    unittest.main()
