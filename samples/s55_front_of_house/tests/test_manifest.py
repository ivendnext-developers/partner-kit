"""S55's manifest: the guest's details read only by the host role (never the app's own user), what the app writes
changed only by the app's user, four buttons for the host on the states they belong to, sending the record's name only;
no notification, report or print naming a guest's field; the one service address; the feed that makes the app's user.

    python3 -m unittest discover -s samples/s55_front_of_house/tests -p 'test_*.py'
"""

import json
import os
import unittest

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")
HOST, INT, SM = "PP FOH Host", "PP FOH Integration", "System Manager"
RES, WAIT = "PP FOH Reservation", "PP FOH Waitlist Entry"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.dt = {d["name"]: d for d in self.m["doctypes"]}
        self.cf = {(c["dt"], c["fieldname"]): c for c in self.m["custom_fields"]}

    def rights(self, doctype, role):
        (p,) = [p for p in self.dt[doctype]["permissions"] if p["role"] == role]
        return sorted(k for k, v in p.items() if v == 1)

    def test_m1_the_guests_details_are_the_hosts_alone(self):
        guest = {(RES, "guest_name"), (RES, "phone"), (RES, "customer"), (RES, "notes"), (WAIT, "guest_name"),
                 (WAIT, "phone"), ("Customer", "pp_foh_guest_notes")}
        for k in guest:
            c = self.cf[k]
            self.assertEqual((sorted(c["read_roles"]), sorted(c["write_roles"])), (sorted([HOST, SM]), sorted([HOST, SM])), k)
            self.assertNotIn(INT, c["read_roles"] + c["write_roles"], k)       # the app's user never reads a guest
            self.assertFalse(c.get("reqd") or c.get("mandatory_depends_on"), k)
        for d in self.m["doctypes"]:                                            # no guest field at the open level
            for f in d["fields"]:
                self.assertNotIn(f["fieldname"], {"guest_name", "phone", "customer", "notes", "email"}, d["name"])
                self.assertNotIn("customer", str(f.get("fetch_from") or ""), d["name"])

    def test_m2_what_the_app_writes_only_the_app_changes(self):
        for k in ((RES, "status"), (RES, "check_name"), (RES, "app_note"), (RES, "seat_key"), (RES, "seat_request"),
                  (WAIT, "check_name"), (WAIT, "app_note"), (WAIT, "seat_key"), (WAIT, "seat_request")):
            c = self.cf[k]
            self.assertEqual(sorted(c["write_roles"]), sorted([INT, SM]), k)
            self.assertNotIn("read_roles", c, k)                                 # everyone reads it
        self.assertEqual(self.cf[(RES, "status")]["default"], "Requested")

    def test_m3_five_buttons_for_the_host_on_their_states_sending_the_name_only(self):
        a = {(d["record_type"], d["label"]): d for d in self.m["desk_actions"]}
        self.assertEqual({k: (v["service"], v["states"]) for k, v in a.items()},
                         {(RES, "Book"): ("book", ["Requested", "Booked"]), (RES, "Seat"): ("seat", ["Requested", "Booked"]),
                          (RES, "No-show"): ("noshow", ["Requested", "Booked"]),
                          (RES, "Cancel booking"): ("cancel", ["Requested", "Booked"]),
                          (RES, "Change booking"): ("change", ["Booked"]),
                          (WAIT, "Seat"): ("seat", ["Waiting", "Table ready"])})
        subs = {s["key"]: s for s in self.m["extension_subscriptions"]}
        for d in a.values():
            self.assertEqual(d["roles"], [HOST])
            self.assertEqual(d["send_fields"], "name")
            self.assertLessEqual(set(d["roles"]), {p["role"] for p in self.dt[d["record_type"]]["permissions"] if p["read"]})
            self.assertEqual((subs[d["service"]]["point"], subs[d["service"]]["timeout_seconds"]), ("desk_action", 10))
            self.assertLessEqual(len(d.get("confirm_text") or ""), 140)

    def test_m4_who_may_do_what_on_the_records(self):
        for dt in (RES, WAIT):
            self.assertEqual(self.rights(dt, INT), ["read", "write"])          # never creates or deletes a booking
            self.assertEqual(self.rights(dt, HOST), ["create", "print", "read", "report", "write"])   # no delete
        self.assertEqual(self.rights("PP FOH Settings", INT), ["read", "write"])     # the press stamp
        self.assertEqual(self.rights("PP FOH Settings", HOST), ["read"])

    def test_m5_nothing_the_manifest_ships_names_a_guests_field(self):
        shipped = json.dumps({k: self.m.get(k) for k in ("notifications", "reports", "print_formats", "number_cards",
                                                        "charts", "links")})
        for f in ("guest_name", "phone", "notes", "guest_notes", '"customer"'):
            self.assertNotIn(f, shipped)
        self.assertNotIn("notifications", self.m)       # the Table ready SMS is the shop's own Notification

    def test_m6_the_one_address_is_the_services(self):
        self.assertEqual(sorted(self.m["allowed_urls"]), sorted(s["endpoint_url"] for s in self.m["extension_subscriptions"]))
        self.assertEqual(len({u.split("/press/")[0] for u in self.m["allowed_urls"]}), 1)

    def test_m7_the_feed_makes_the_apps_user_and_keeps_a_description_the_shop_keeps(self):
        (r,) = self.m["registered_applications"]
        self.assertLessEqual(len(r["description"]), 140)
        self.assertEqual(r["events"], [RES])

    def test_m9_no_version_history_and_a_booked_slot_is_read_only_in_the_form(self):
        for d in self.m["doctypes"]:                 # a Version diff would hand a guest's field to any reader
            self.assertNotIn("track_changes", d, d["name"])
        f = {x["fieldname"]: x for x in self.dt[RES]["fields"]}
        for k in ("booking_date", "booking_time", "minutes", "place"):
            self.assertIn('doc.status=="Booked"', f[k].get("read_only_depends_on") or "", k)

    def test_m8_the_store_row_carries_the_register_and_the_rules(self):
        f = {x["fieldname"]: x for x in self.dt["PP FOH Store"]["fields"]}
        self.assertEqual((f["register"]["options"], f["register"]["reqd"]), ("POS Profile", 1))
        self.assertEqual((f["second_check"]["fieldtype"], f["second_check"].get("default")), ("Check", None))   # off
        self.assertEqual(f["no_show_deposit"]["options"].split("\n"), ["Keep it", "Return it"])
        place = {x["fieldname"]: x for x in self.dt[RES]["fields"]}["place"]
        self.assertEqual(place["options"], "Retail Floor Place")


if __name__ == "__main__":
    unittest.main()
