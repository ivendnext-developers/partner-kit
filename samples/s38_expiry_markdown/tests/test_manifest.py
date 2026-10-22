"""S38's manifest: the four step fields are on Item Group, the button is on the Batch list and a lot's form for the shop's
stock and price managers and sends no more than each lot's name, item and expiry date, the settings name the price
list, and the one address is the service's.

    python3 -m unittest discover -s samples/s38_expiry_markdown/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)

    def test_the_steps_are_four_fields_on_item_group(self):
        fields = {f["fieldname"]: f for f in self.m["custom_fields"]}
        self.assertEqual({f["dt"] for f in fields.values()}, {"Item Group"})
        self.assertEqual({k: f["fieldtype"] for k, f in fields.items()},
                         {"pp_exm_days_1": "Int", "pp_exm_pct_1": "Percent", "pp_exm_days_2": "Int", "pp_exm_pct_2": "Percent"})

    def test_the_button_is_on_lots_and_sends_only_their_name_item_and_date(self):
        a, = self.m["desk_actions"]
        self.assertEqual((a["record_type"], a["placement"], a["on_draft"], a["on_submitted"]), ("Batch", "both", 1, 0))
        self.assertEqual([x.strip() for x in a["send_fields"].split(",")], ["name", "item", "expiry_date"])
        self.assertEqual(a["roles"], ["Item Manager"])     # the shop role that reads Batch (a press re-checks the read)
        self.assertLessEqual(len(a["confirm_text"]), 140)
        sub, = self.m["extension_subscriptions"]
        self.assertEqual((sub["point"], sub["key"], sub["timeout_seconds"]), ("desk_action", a["service"], 10))

    def test_the_settings_name_a_price_list_and_the_apps_role_only_reads_them(self):
        d, = self.m["doctypes"]
        price = {f["fieldname"]: f for f in d["fields"]}["price_list"]
        self.assertEqual((price["fieldtype"], price["options"], price["reqd"]), ("Link", "Price List", 1))
        role, = [p for p in d["permissions"] if p["role"] == "PP EXM Integration"]
        self.assertEqual([k for k, v in role.items() if v == 1], ["read"])

    def test_the_one_address_is_the_services(self):
        self.assertEqual(self.m["allowed_urls"], [self.m["extension_subscriptions"][0]["endpoint_url"]])


if __name__ == "__main__":
    unittest.main()
