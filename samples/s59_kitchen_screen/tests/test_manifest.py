"""S59's manifest: what makes a link work changed only by the app's user, one button for the manager sending the
record's name only, no field on any record not the app's own, no guest field, the one service address, and the feed
that makes the app's user.

    python3 -m unittest discover -s samples/s59_kitchen_screen/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")
MGR, INT, SM = "PP KSC Manager", "PP KSC Integration", "System Manager"
SCREEN, SET, STORE, STN = "PP KSC Screen", "PP KSC Settings", "PP KSC Store", "PP KSC Screen Station"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.dt = {d["name"]: d for d in self.m["doctypes"]}
        self.cf = {(c["dt"], c["fieldname"]): c for c in self.m["custom_fields"]}

    def rights(self, doctype, role):
        (p,) = [p for p in self.dt[doctype]["permissions"] if p["role"] == role]
        return sorted(k for k, v in p.items() if v == 1)

    def test_m1_what_makes_a_link_work_only_the_app_writes(self):
        for f in ("number", "link", "made_for"):
            c = self.cf[(SCREEN, f)]
            self.assertEqual(sorted(c["write_roles"]), sorted([INT, SM]), f)
            self.assertNotIn(MGR, c["write_roles"], f)        # a manager who could lower the number revives a leaked link
        self.assertFalse([c for c in self.m["custom_fields"] if c["dt"] != SCREEN])   # no field on any record not its own

    def test_m2_one_button_for_the_manager_sending_the_name_only(self):
        (a,) = self.m["desk_actions"]
        self.assertEqual((a["record_type"], a["label"], a["roles"], a["send_fields"], a["service"]),
                         (SCREEN, "Make link", [MGR], "name", "link"))
        (s,) = self.m["extension_subscriptions"]
        self.assertEqual((s["key"], s["point"]), ("link", "desk_action"))
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"]])

    def test_m3_the_app_user_reads_its_settings_and_writes_only_its_screens(self):
        self.assertEqual(self.rights(SET, INT), ["read"])
        self.assertEqual(self.rights(SCREEN, INT), ["read", "write"])
        self.assertEqual(self.rights(SET, MGR), ["read"])
        self.assertNotIn("create", self.rights(SCREEN, INT))

    def test_m4_one_feed_that_makes_the_apps_user(self):
        (f,) = self.m["registered_applications"]
        self.assertEqual(f["events"], [SCREEN])
        self.assertIn("leave the feed off", f["description"])

    def test_m5_no_guest_field_and_no_money_anywhere(self):
        words = json.dumps([d["fields"] for d in self.m["doctypes"]]).lower()
        for w in ("phone", "email", "e-mail", "price", "amount", "rate", "customer"):
            self.assertNotIn(f'"{w}', words, w)

    def test_m6_a_station_screen_must_name_its_stations(self):
        (f,) = [f for f in self.dt[SCREEN]["fields"] if f["fieldname"] == "stations"]
        self.assertEqual((f["options"], f["mandatory_depends_on"]), (STN, "eval:doc.kind=='Station'"))
        (s,) = self.dt[STN]["fields"]
        self.assertEqual((s["options"], s["reqd"]), ("Retail Kitchen Station", 1))

    def test_m7_sold_out_is_off_unless_the_store_ticks_it(self):
        (f,) = [f for f in self.dt[STORE]["fields"] if f["fieldname"] == "sold_out_on"]
        self.assertNotIn("default", f)
        self.assertIn("does not limit to its stores", f["description"])


if __name__ == "__main__":
    unittest.main()
