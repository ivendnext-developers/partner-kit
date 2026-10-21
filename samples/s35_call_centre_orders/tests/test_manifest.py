"""S35's manifest: the one field it adds is the Serving store on Territory (a link to Warehouse), the button is on a
draft Sales Order's form only and sends no more than the order's name and territory, and the feed whose user a service
serving many shops receives on Connect again follows sales orders and installs switched off (the shop leaves it off).

    python3 -m unittest discover -s samples/s35_call_centre_orders/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.m = json.load(open(MANIFEST))

    def test_the_serving_store_is_a_link_to_warehouse_on_territory(self):
        f, = self.m["custom_fields"]
        self.assertEqual((f["dt"], f["fieldtype"], f["options"]), ("Territory", "Link", "Warehouse"))
        self.assertTrue(f["fieldname"].startswith(self.m["app"] + "_"))

    def test_the_button_is_on_a_drafts_form_and_sends_only_the_name_and_territory(self):
        a, = self.m["desk_actions"]
        self.assertEqual((a["record_type"], a["placement"], a["on_draft"], a["on_submitted"]), ("Sales Order", "form", 1, 0))
        self.assertEqual([x.strip() for x in a["send_fields"].split(",")], ["name", "territory"])
        self.assertEqual(sorted(a["roles"]), ["Sales Manager", "Sales User"])     # shop roles: the install makes none
        sub, = self.m["extension_subscriptions"]
        self.assertEqual((sub["point"], sub["key"]), ("desk_action", a["service"]))

    def test_the_feed_follows_sales_orders_and_the_one_address_is_the_services(self):
        feed, = self.m["registered_applications"]
        self.assertEqual(feed["events"], ["Sales Order"])       # the checker refuses a feed with none; left off, it records nothing
        self.assertEqual(self.m["allowed_urls"], [self.m["extension_subscriptions"][0]["endpoint_url"]])


if __name__ == "__main__":
    unittest.main()
