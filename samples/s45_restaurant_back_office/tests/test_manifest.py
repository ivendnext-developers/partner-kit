"""S45's manifest: the allergen field on Item and the issue link on Stock Entry; three buttons, each on its own record
for the roles that run it and sending no more than it needs; the press stamp the app's role may write; the issues
written only by the app's role; the one service address.

    python3 -m unittest discover -s samples/s45_restaurant_back_office/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")
INT = "PP RBO Integration"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.dt = {d["name"]: d for d in self.m["doctypes"]}

    def rights(self, doctype, role):
        (p,) = [p for p in self.dt[doctype]["permissions"] if p["role"] == role]
        return sorted(k for k, v in p.items() if v == 1)

    def test_m1_the_two_fields_on_the_shops_records(self):
        f = {(c["dt"], c["fieldname"]): c for c in self.m["custom_fields"]}
        self.assertEqual(sorted(f), [("Item", "pp_rbo_allergens"), ("Stock Entry", "pp_rbo_issue")])
        self.assertEqual(f[("Item", "pp_rbo_allergens")]["fieldtype"], "Data")    # a till field rule shows Data
        link = f[("Stock Entry", "pp_rbo_issue")]
        self.assertEqual((link["fieldtype"], link["options"], link["read_only"]), ("Link", "PP RBO Issue", 1))

    def test_m2_three_buttons_each_on_its_record_sending_no_more_than_it_needs(self):
        a = {d["label"]: d for d in self.m["desk_actions"]}
        self.assertEqual({k: (v["record_type"], v["placement"], [x.strip() for x in v["send_fields"].split(",")])
                          for k, v in a.items()},
                         {"Issue ingredients": ("PP RBO Settings", "form", ["name", "company"]),
                          "Work out food cost": ("PP RBO Food Cost", "form", ["name", "store", "from_date", "to_date"]),
                          "Check allergens": ("Item", "both", ["name", "item_name"])})
        subs = {s["key"]: s for s in self.m["extension_subscriptions"]}
        for d in a.values():
            self.assertEqual((subs[d["service"]]["point"], subs[d["service"]]["timeout_seconds"]), ("desk_action", 10))
            self.assertLessEqual(len(d.get("confirm_text") or ""), 140)

    def test_m3_a_buttons_roles_can_read_its_record(self):
        a = {d["label"]: d for d in self.m["desk_actions"]}
        for label in ("Issue ingredients", "Work out food cost"):
            d = a[label]
            readers = {p["role"] for p in self.dt[d["record_type"]]["permissions"] if p.get("read")}
            self.assertLessEqual(set(d["roles"]), readers, label)

    def test_m4_only_the_apps_role_makes_issues_and_no_one_deletes_them(self):
        for p in self.dt["PP RBO Issue"]["permissions"]:
            if p["role"] != INT:
                self.assertFalse(p.get("create") or p.get("delete"), p["role"])
            self.assertFalse(p.get("delete"), p["role"])       # a deleted issue would let its sales be issued again
        self.assertEqual(self.rights("PP RBO Issue", INT), ["create", "read", "write"])
        self.assertEqual(self.rights("PP RBO Issue", "Stock Manager"), ["print", "read", "report", "write"])   # Left out
        self.assertEqual(self.rights("PP RBO Settings", INT), ["read", "write"])     # the press stamp
        self.assertEqual(self.rights("PP RBO Food Cost", INT), ["read", "write"])
        self.assertEqual(self.rights("PP RBO Allergen Check", INT), ["create", "read"])
        self.assertIn("Left out", {f["fieldname"]: f for f in self.dt["PP RBO Issue"]["fields"]}["status"]["options"])

    def test_m4b_money_in_the_companys_currency(self):
        for dt in ("PP RBO Issue", "PP RBO Food Cost", "PP RBO Issue Line", "PP RBO Food Cost Line"):
            for f in self.dt[dt]["fields"]:
                if f["fieldtype"] == "Currency":
                    self.assertEqual(f.get("options"), "currency", (dt, f["fieldname"]))
        for dt in ("PP RBO Issue", "PP RBO Food Cost"):
            cur = {f["fieldname"]: f for f in self.dt[dt]["fields"]}["currency"]
            self.assertEqual(cur["fetch_from"], "company.default_currency")

    def test_m5_the_start_moment_is_required(self):
        f = {x["fieldname"]: x for x in self.dt["PP RBO Settings"]["fields"]}
        self.assertEqual((f["start_from"]["fieldtype"], f["start_from"]["reqd"]), ("Datetime", 1))
        self.assertEqual(f["run_started"]["read_only"], 1)

    def test_m6_the_one_address_is_the_services(self):
        self.assertEqual(sorted(self.m["allowed_urls"]), sorted(s["endpoint_url"] for s in self.m["extension_subscriptions"]))
        self.assertEqual(len({u.split("/press/")[0] for u in self.m["allowed_urls"]}), 1)

    def test_m7_a_feed_description_the_shop_keeps(self):
        (r,) = self.m["registered_applications"]
        self.assertLessEqual(len(r["description"]), 140)      # the shop refuses a longer one at install (bench, run 1)


if __name__ == "__main__":
    unittest.main()
