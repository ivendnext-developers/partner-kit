"""S25's manifest: valid for the kit's checker; the Card named by its key (the shop refuses a second card); every
field the service reads or writes is declared; the app's user holds only what it needs; help on each record type; nothing
the shop sends outside.

    python3 -m unittest discover -s samples/s25_gift_on_spend/tests -p 'test_*.py'
"""

import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SAMPLE = HERE.parent
KIT = SAMPLE.parent.parent
M = json.loads((SAMPLE / "manifest.json").read_text())
DT = {d["name"]: d for d in M["doctypes"]}
CARD, SETTINGS = DT["PP GCS Card"], DT["PP GCS Settings"]
FIELDS = {n: {f["fieldname"]: f for f in d["fields"]} for n, d in DT.items()}


class Manifest(unittest.TestCase):
    def test_the_kits_checker_finds_it_valid(self):
        out = subprocess.run([sys.executable, str(KIT / "tools" / "manifest" / "validate.py"), str(SAMPLE / "manifest.json")],
                             capture_output=True, text=True)
        self.assertEqual((out.returncode, out.stdout.strip()), (0, "VALID"), out.stdout + out.stderr)

    def test_a_card_is_named_by_its_key_so_the_shop_refuses_a_second(self):
        self.assertEqual(CARD["autoname"], "field:card_key")
        self.assertEqual((FIELDS["PP GCS Card"]["card_key"].get("unique"), FIELDS["PP GCS Card"]["card_key"].get("reqd")), (1, 1))

    def test_every_card_field_the_service_writes_is_declared(self):
        src = (SAMPLE / "service" / "cards.py").read_text()
        written = set(re.findall(r'"(\w+)": ', src.split("def issue_one")[1].split("# ---------- 3")[0])) - {"doctype"}
        for at in [m.end() for m in re.finditer(r"_set\(t, rec, ", src)]:
            depth, i = 1, at
            while depth:
                depth += {"(": 1, ")": -1}.get(src[i], 0)
                i += 1
            written |= set(re.findall(r"(?:^|, |\n\s*)(\w+)=", src[at:i - 1]))
        card_written = written - {"serial_number", "item_code", "total", "balance", "first_name"}
        self.assertTrue(card_written <= set(FIELDS["PP GCS Card"]), card_written - set(FIELDS["PP GCS Card"]))
        self.assertIn("release_after_utc", card_written)

    def test_every_setting_the_rules_read_is_declared(self):
        src = (SAMPLE / "service" / "gcs.py").read_text()
        read = set(re.findall(r'raw(?:\.get\("|\[")(\w+)"', src))
        self.assertEqual(read - set(FIELDS["PP GCS Settings"]), set())
        self.assertGreaterEqual(len(read), 10)

    def test_the_apps_user_reads_the_settings_and_writes_only_its_cards(self):
        perms = {d: {p["role"]: {k for k, v in p.items() if v == 1} for p in DT[d]["permissions"]} for d in DT}
        self.assertEqual(perms["PP GCS Settings"]["PP GCS Integration"], {"read"})
        self.assertEqual(perms["PP GCS Card"]["PP GCS Integration"], {"read", "write", "create"})
        self.assertNotIn("write", perms["PP GCS Card"]["System Manager"])     # staff read the cards; the service writes

    def test_each_record_type_carries_its_help_address(self):
        ps = {p["doc_type"]: p["value"] for p in M["property_setters"] if p["property"] == "documentation"}
        self.assertEqual(set(ps), set(DT))
        for v in ps.values():
            self.assertTrue(v.startswith("https://developer.ivendnext.com/recipes/gift_card_on_spend.html#"), v)

    def test_the_cards_show_under_the_customer_and_the_sale(self):
        self.assertEqual({(l["doctype"], l["link_fieldname"]) for l in M["links"]}, {("Customer", "customer"), ("POS Invoice", "sale")})

    def test_the_shop_calls_nothing_outside_and_names_the_one_service_its_site_connects(self):
        for k in ("extension_subscriptions", "remote_keys", "webhooks", "notifications"):
            self.assertFalse(M.get(k), k)
        # the hosted handshake goes only to an address in allowed_urls (POS extension_package._hosted_origins)
        self.assertEqual(M["allowed_urls"], ["https://gcs.partner.example"])
        self.assertEqual(M["registered_applications"][0]["events"], ["POS Invoice"])

    def test_the_setup_and_what_leaves_are_in_the_description(self):
        for words in ("PP GCS Integration", "read and create on Gift Card", "submit on Gift Card Balance", "PP GCS Sales",
                      "What leaves the shop", "set the balance of any gift card"):
            self.assertIn(words, M["description"])
        self.assertNotIn("Nothing leaves", M["description"])
        self.assertNotIn("<", json.dumps(M))


if __name__ == "__main__":
    unittest.main()
