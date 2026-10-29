"""S56's manifest: what the app writes on a code changed only by the app's user, one button for the manager sending the
record's name only, the table card printing only the code's own picture, no guest field anywhere, the one service
address, and the feed that makes the app's user.

    python3 -m unittest discover -s samples/s56_guest_ordering/tests -p 'test_*.py'
"""

import json
import os
import unittest

try:
    import jinja2
except ImportError:          # the kit's CI installs it; on a laptop without it the card's render tests skip
    jinja2 = None

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")
MGR, INT, SM = "PP GOR Manager", "PP GOR Integration", "System Manager"
CODE, SET, STORE = "PP GOR Code", "PP GOR Settings", "PP GOR Store"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.dt = {d["name"]: d for d in self.m["doctypes"]}
        self.cf = {(c["dt"], c["fieldname"]): c for c in self.m["custom_fields"]}

    def rights(self, doctype, role):
        (p,) = [p for p in self.dt[doctype]["permissions"] if p["role"] == role]
        return sorted(k for k, v in p.items() if v == 1)

    def test_m1_what_makes_a_code_work_only_the_app_writes(self):
        for f in ("number", "link", "made_for", "qr"):
            c = self.cf[(CODE, f)]
            self.assertEqual(sorted(c["write_roles"]), sorted([INT, SM]), f)
            self.assertNotIn(MGR, c["write_roles"], f)        # a manager who could lower the number revives a leaked code
        self.assertFalse([c for c in self.m["custom_fields"] if c["dt"] != CODE])   # no field on any record not its own

    def test_m2_one_button_for_the_manager_sending_the_name_only(self):
        (a,) = self.m["desk_actions"]
        self.assertEqual((a["record_type"], a["label"], a["service"], a["roles"], a["send_fields"]),
                         (CODE, "Make code", "code", [MGR], "name"))
        (s,) = self.m["extension_subscriptions"]
        self.assertEqual((s["key"], s["point"], s["timeout_seconds"]), ("code", "desk_action", 10))
        self.assertLessEqual(len(a["confirm_text"]), 140)

    def test_m3_who_may_do_what(self):
        self.assertEqual(self.rights(CODE, INT), ["read", "write"])          # never makes or deletes a code
        self.assertEqual(self.rights(CODE, MGR), ["create", "delete", "print", "read", "report", "write"])
        self.assertEqual(self.rights(SET, INT), ["read"])
        self.assertEqual(self.rights(SET, MGR), ["read"])

    def test_m4_the_table_card_prints_the_codes_own_picture_and_nothing_from_outside(self):
        (p,) = self.m["print_formats"]
        self.assertEqual(p["doc_type"], CODE)
        self.assertIn('src="{{ doc.qr }}"', p["html"])
        self.assertNotIn("http", p["html"])

    @unittest.skipUnless(jinja2, "the template engine is not installed here")
    def test_m9_the_card_prints_the_qr_only_for_the_record_and_table_it_was_made_for(self):
        (p,) = self.m["print_formats"]
        tpl = jinja2.Environment(autoescape=False).from_string(p["html"])

        class Doc(dict):
            __getattr__ = dict.get

        made = Doc(name="GOR-CODE-00001", kind="Table", store="S", place="FP-T12", place_label="Table 12", number=3,
                   kiosk_name="", link="https://x/#s=a&t=GOR-CODE-00001.3.sig", qr="data:image/svg+xml;base64,AAAA",
                   made_for="Table|S|FP-T12")
        render = lambda d: tpl.render(doc=d, _=lambda s: s)
        self.assertIn('src="data:image/svg+xml;base64,AAAA"', render(made))
        copied = Doc(made, name="GOR-CODE-00002", place="FP-T13", place_label="Table 13")      # Desk's Duplicate
        self.assertNotIn("<img", render(copied))
        self.assertIn("Press Make code first.", render(copied))
        self.assertNotIn("<img", render(Doc(made, place="FP-T13")))                             # its table changed
        kiosk = Doc(made, kind="Kiosk", place="", kiosk_name=" Door ", made_for="Kiosk|S|Door")
        self.assertIn("<img", render(kiosk))
        self.assertIn("&lt;b&gt;", render(Doc(made, place_label="<b>x</b>")))             # a name is text

    def test_m5_no_guest_field_anywhere(self):
        names = [f["fieldname"] for d in self.m["doctypes"] for f in d["fields"]] + [c["fieldname"] for c in self.m["custom_fields"]]
        options = [f.get("options") for d in self.m["doctypes"] for f in d["fields"]]
        for f in ("phone", "email", "guest_name", "customer", "mobile", "mobile_no", "name_of_guest"):
            self.assertNotIn(f, names)
        self.assertNotIn("Customer", options)
        for d in self.m["doctypes"]:
            self.assertNotIn("track_changes", d, d["name"])

    def test_m6_the_one_address_is_the_services(self):
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"] for s in self.m["extension_subscriptions"]])

    def test_m7_the_feed_makes_the_apps_user(self):
        (r,) = self.m["registered_applications"]
        self.assertLessEqual(len(r["description"]), 140)
        self.assertEqual(r["events"], [CODE])

    def test_m8_the_store_row_carries_the_register_and_the_limits(self):
        f = {x["fieldname"]: x for x in self.dt[STORE]["fields"]}
        self.assertEqual((f["register"]["options"], f["register"]["reqd"]), ("POS Profile", 1))
        self.assertEqual((f["tables_on"].get("default"), f["kiosk_on"].get("default")), ("1", None))
        place = {x["fieldname"]: x for x in self.dt[CODE]["fields"]}["place"]
        self.assertEqual(place["options"], "Retail Floor Place")


if __name__ == "__main__":
    unittest.main()
