"""S24's manifest: valid for the kit's checker, one record type the service can read and nothing it cannot, the fields the
service reads are the ones the record fetches, help on the record type, and nothing the shop sends outside but the hosted handshake.

    python3 -m unittest discover -s samples/s24_price_checker/tests -p 'test_*.py'
"""

import json
import subprocess
import sys
import os
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent
KIT = SAMPLE.parent.parent
sys.path.insert(0, str(SAMPLE))
import price  # noqa: E402

M = json.loads((SAMPLE / "manifest.json").read_text())
KIOSK = next(d for d in M["doctypes"] if d["name"] == "PP PRC Kiosk")
FIELDS = {f["fieldname"]: f for f in KIOSK["fields"]}


class Manifest(unittest.TestCase):
    def test_the_kits_checker_finds_it_valid(self):
        out = subprocess.run([sys.executable, str(KIT / "tools" / "manifest" / "validate.py"), str(SAMPLE / "manifest.json")],
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "VALID"), out.stdout + out.stderr)

    def test_the_kiosks_name_is_the_frameworks_random_name(self):
        self.assertEqual(KIOSK["autoname"], "hash")

    def test_every_field_the_service_reads_is_fetched_from_the_till_profile(self):
        read = {"company", "selling_price_list", "currency", "customer", "warehouse"}
        for f in read:
            self.assertEqual(FIELDS[f].get("fetch_from"), f"pos_profile.{f}", f)
            self.assertEqual(FIELDS[f].get("read_only"), 1, f)
        self.assertEqual(FIELDS["pos_profile"]["options"], "POS Profile")
        k = price.kiosk_of({f: "x" for f in read} | {"enabled": 1})
        self.assertEqual(set(k) - {"pos_profile"}, read)       # what kiosk_of reads is what the record holds

    def test_the_apps_role_carries_its_reads_in_the_manifest(self):
        rights = {(r["doctype"], r["role"]): r["rights"] for r in M["role_rights"]}
        self.assertEqual(rights, {("Item", "PP PRC Integration"): ["read"], ("Item Price", "PP PRC Integration"): ["read"]})

    def test_the_apps_user_may_only_read_the_kiosks(self):
        perms = {p["role"]: p for p in KIOSK["permissions"]}
        self.assertEqual({k for k, v in perms["PP Integration"].items() if v == 1}, {"read"})

    def test_the_record_type_carries_its_help_address(self):
        ps = [p for p in M["property_setters"] if p["doc_type"] == "PP PRC Kiosk" and p["property"] == "documentation"]
        self.assertEqual(len(ps), 1)
        self.assertTrue(ps[0]["value"].startswith("https://developer.ivendnext.com/recipes/price_checker.html#"))

    def test_the_shop_sends_nothing_outside_but_the_handshake(self):
        for k in ("extension_subscriptions", "remote_keys", "webhooks"):
            self.assertFalse(M.get(k), k)
        # the hosted handshake goes only to an address in allowed_urls (POS extension_package._hosted_origins): the
        # service's own, once; without it a hosted copy is never connected and every kiosk says it is not set up
        self.assertEqual(M.get("allowed_urls"), ["https://prc.partner.example"])
        self.assertEqual(M["registered_applications"][0]["events"], ["PP PRC Kiosk"])

    def test_the_setup_is_in_the_description(self):
        for words in ("PP Integration before this is installed", "PP PRC Kiosk feed", "read on Item and Item Price", "writes nothing"):
            self.assertIn(words, M["description"])
        self.assertNotIn("<", json.dumps(M))

    def test_the_english_words_cover_every_name_the_store_sees(self):   # Desk shows people's words, never the code
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        names = {d["name"] for d in m.get("doctypes", [])}
        for key in ("print_formats", "reports", "registered_applications", "sale_attributes", "workspaces",
                    "number_cards", "notifications", "dashboard_charts"):
            names |= {x["name"] for x in m.get(key, [])}
        for wf in m.get("workflows", []):
            names |= {wf["name"]} | {s["state"] for s in wf["states"]} | {t["action"] for t in wf["transitions"]}
        for d in m.get("doctypes", []):
            names |= {p["role"] for p in d.get("permissions", []) if not p["role"].endswith(" Integration")}
        (en,) = [t["words"] for t in m["translations"] if t["language"] == "en"]
        self.assertEqual(sorted(n for n in names if n.startswith(m["prefix"]) and n not in en), [])
        self.assertTrue(all(w and not w.startswith(m["prefix"]) for w in en.values()))


if __name__ == "__main__":
    unittest.main()
