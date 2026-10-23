"""S44's manifest: one campaign record type and its three tables, two buttons on the campaign's form for the app's
manager role, sending no more than the campaign's name, the draw hidden once drawn, the rule locked once drawn, the
results' customer details fetched by the shop, and the two addresses the services'.

    python3 -m unittest discover -s samples/s44_lucky_draw/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")
RULE = ["company", "hours_from_utc", "from_date", "to_date", "spend_per_entry", "most_entries_per_sale", "winners",
        "reserves", "tills", "customer_groups"]


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.types = {d["name"]: d for d in self.m["doctypes"]}
        self.c = {f["fieldname"]: f for f in self.types["PP LDW Campaign"]["fields"]}

    def test_one_campaign_and_three_tables(self):
        self.assertEqual(sorted(self.types), ["PP LDW Campaign", "PP LDW Campaign Group", "PP LDW Campaign Till",
                                              "PP LDW Result"])
        self.assertEqual(sorted(n for n, d in self.types.items() if d.get("istable")),
                         ["PP LDW Campaign Group", "PP LDW Campaign Till", "PP LDW Result"])
        self.assertEqual((self.c["tills"]["options"], self.c["customer_groups"]["options"], self.c["results"]["options"]),
                         ("PP LDW Campaign Till", "PP LDW Campaign Group", "PP LDW Result"))

    def test_the_buttons_are_on_the_campaigns_form_for_its_manager_and_send_only_its_name(self):
        count, drawn = self.m["desk_actions"]
        for a, label, service in ((count, "Count entries", "count"), (drawn, "Draw winners", "draw")):
            self.assertEqual((a["record_type"], a["label"], a["placement"], a["service"], a["roles"], a["send_fields"]),
                             ("PP LDW Campaign", label, "form", service, ["PP LDW Manager"], "name"))
        self.assertEqual(drawn["conditions"], [{"field": "status", "operator": "!=", "value": "Drawn"}])
        self.assertNotIn("conditions", count)
        self.assertLessEqual(len(drawn["confirm_text"]), 140)
        subs = {s["key"]: s for s in self.m["extension_subscriptions"]}
        self.assertEqual({k: (s["point"], s["timeout_seconds"]) for k, s in subs.items()},
                         {"count": ("desk_action", 10), "draw": ("desk_action", 10)})

    def test_the_rule_is_locked_once_drawn_and_the_service_alone_writes_the_record(self):
        for f in RULE:
            self.assertEqual(self.c[f].get("read_only_depends_on"), "eval:doc.status=='Drawn'", f)
        for f in ("status", "counted_on", "sales_counted", "customers_counted", "entries_counted", "count_fingerprint",
                  "drawn_on", "drawn_by", "draw_entries", "draw_fingerprint", "drawn_numbers"):
            self.assertEqual(self.c[f].get("read_only"), 1, f)
        res = {f["fieldname"]: f for f in self.types["PP LDW Result"]["fields"]}
        self.assertEqual(sorted(k for k, f in res.items() if not f.get("read_only")), ["handed_over", "handed_over_on"])

    def test_the_results_customer_details_are_the_shops_own_fetched_on_save(self):
        res = {f["fieldname"]: f for f in self.types["PP LDW Result"]["fields"]}
        self.assertEqual({k: res[k]["fetch_from"] for k in ("customer_name", "mobile_no", "email_id")},
                         {"customer_name": "customer.customer_name", "mobile_no": "customer.mobile_no",
                          "email_id": "customer.email_id"})

    def test_the_manager_runs_campaigns_and_the_apps_role_reads_and_writes_them_only(self):
        perms = {p["role"]: p for p in self.types["PP LDW Campaign"]["permissions"]}
        self.assertEqual(sorted(perms), ["PP LDW Integration", "PP LDW Manager", "System Manager"])
        self.assertEqual(sorted(k for k, v in perms["PP LDW Integration"].items() if v == 1), ["read", "write"])
        self.assertEqual(perms["PP LDW Manager"]["create"], 1)

    def test_the_addresses_are_the_services(self):
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"] for s in self.m["extension_subscriptions"]])


if __name__ == "__main__":
    unittest.main()
