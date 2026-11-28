"""S64's manifest: the record types the service reads and writes, the two fields on the retailer's records, the two
buttons, the four reports, the rights the service needs and no more, and the words Desk shows.

    python3 -m unittest discover -s samples/s64_production_station/tests -p 'test_*.py'
"""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [SAMPLE, os.path.join(SAMPLE, "..", "..", "tools", "manifest")]
import pst  # noqa: E402
from validate import validate  # noqa: E402

FEED = {"name": "PP PST Production station feed",
        "description": "the production station service reads the settings and items and writes the tags, carts, stock "
                       "entries and report rows as this user",
        "events": ["PP PST Station"], "reads_events": False}
INT, MGR = "PP PST Integration", "PP PST Manager"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(SAMPLE, "manifest.json"), encoding="utf-8") as f:
            self.m = json.load(f)
        self.types = {d["name"]: d for d in self.m["doctypes"]}
        self.fields = {n: {f["fieldname"]: f for f in d["fields"]} for n, d in self.types.items()}

    def test_the_kits_copy_of_the_shops_checker_takes_the_whole_manifest(self):
        self.assertEqual(validate(self.m), [])
        self.assertEqual((self.m["manifest_version"], self.m["app"], self.m["prefix"]), (2, "pp_pst", "PP PST"))

    def test_the_settings_hold_what_the_service_reads(self):
        s = self.fields["PP PST Settings"]
        self.assertEqual(self.types["PP PST Settings"]["autoname"], "field:company")
        want = {"company", "currency", "room", "tag_width_mm", "tag_height_mm", "first_week", "colours", "day_colour",
                "day_colour_on", "workers", "price_points", "places"}
        self.assertEqual({k for k, f in s.items() if f["fieldtype"] != "Section Break"}, want)
        self.assertEqual((s["tag_width_mm"]["default"], s["tag_height_mm"]["default"]), ("50", "30"))
        self.assertEqual({k: s[k]["options"] for k in ("colours", "workers", "price_points", "places")},
                         {"colours": "PP PST Colour", "workers": "PP PST Worker", "price_points": "PP PST Price Point",
                          "places": "PP PST Destination"})
        self.assertEqual(set(self.fields["PP PST Colour"]), {"colour"})
        self.assertEqual(set(self.fields["PP PST Worker"]), {"worker_name", "active"})
        self.assertEqual(set(self.fields["PP PST Price Point"]), {"category", "price"})
        self.assertEqual(set(self.fields["PP PST Destination"]), {"warehouse", "label"})
        self.assertEqual(s["currency"]["fetch_from"], "company.default_currency")

    def test_a_tag_holds_every_field_the_service_writes_and_none_a_person_types(self):
        t = self.fields["PP PST Tag"]
        self.assertEqual(set(t), {"station", "worker", "category", "item", "colour", "week_start", "price", "quantity",
                                  "barcode", "tagged_on", "hour", "cart", "void", "req"})
        self.assertTrue(t["req"].get("unique") and t["req"].get("hidden"))   # one tag a tap, a lost answer's too
        self.assertTrue(all(f.get("read_only") for f in t.values()))
        self.assertEqual(self.types["PP PST Tag"]["autoname"], "format:PST-T-{########}")

    def test_a_cart_has_one_open_cart_a_station_and_pounds_a_lead_types(self):
        c = self.fields["PP PST Cart"]
        self.assertEqual(c["state"]["options"].split("\n"), ["Open", "Received", "Sent"])
        self.assertTrue(c["open_for"].get("unique") and c["open_for"].get("hidden"))
        self.assertFalse(c["pounds"].get("read_only"))
        self.assertTrue(all(f.get("read_only") for k, f in c.items() if k != "pounds"))
        self.assertEqual((c["receipt"]["options"], c["transfer"]["options"]), ("Stock Entry", "Stock Entry"))

    def test_the_series_of_each_record(self):
        self.assertEqual({n: d.get("autoname") for n, d in self.types.items() if not d.get("istable")},
                         {"PP PST Settings": "field:company", "PP PST Station": "format:PST-S-{#####}",
                          "PP PST Tag": "format:PST-T-{########}", "PP PST Cart": "format:PST-C-{#####}",
                          "PP PST Report": "format:PST-R-{#####}"})

    def test_the_report_rows_are_the_ones_work_out_writes(self):
        rows = pst.worker_rows([{"tagged_on": "2026-11-04", "station": "S", "worker": "W", "hour": 9, "pieces": 1}])
        self.assertEqual(set(rows[0]), set(self.fields["PP PST Worker Row"]))
        import datetime
        crow = pst.colour_rows([("Blue", datetime.date(2026, 11, 2))], {}, {})
        self.assertEqual(set(crow[0]), set(self.fields["PP PST Colour Row"]))
        r = self.fields["PP PST Report"]
        self.assertEqual((r["worker_rows"]["options"], r["colour_rows"]["options"]), ("PP PST Worker Row", "PP PST Colour Row"))

    def test_the_two_fields_on_the_retailers_records(self):
        cf = {(f["dt"], f["fieldname"]): f for f in self.m["custom_fields"]}
        colour, cart = cf[("Item", pst.FIELD_COLOUR)], cf[("Stock Entry", pst.FIELD_CART)]
        # Small Text: a short text field takes 562 bytes of the shop's Item row, Small Text 10 (guide 07)
        self.assertEqual((colour["fieldtype"], colour["label"]), ("Small Text", "Tag colour"))
        self.assertNotIn("length", colour)
        self.assertEqual((cart["fieldtype"], cart["options"], cart["read_only"], cart["no_copy"]), ("Link", "PP PST Cart", 1, 1))
        self.assertEqual(sorted(k for k in cf if k[0] not in ("PP PST Station",)), [("Item", "pp_pst_tag_colour"),
                                                                                  ("Stock Entry", "pp_pst_cart")])
        self.assertEqual(sorted(k[1] for k in cf if k[0] == "PP PST Station"), ["link", "made_for", "number"])

    def test_two_buttons_for_the_lead_and_one_address(self):
        acts = {a["label"]: a for a in self.m["desk_actions"]}
        self.assertEqual(sorted(acts), ["Make link", "Work out"])
        self.assertEqual((acts["Make link"]["record_type"], acts["Make link"]["service"]), ("PP PST Station", "link"))
        self.assertEqual((acts["Work out"]["record_type"], acts["Work out"]["service"]), ("PP PST Report", "work"))
        for a in acts.values():
            self.assertEqual((a["roles"], a["send_fields"]), ([MGR, "System Manager"], "name"))
            readers = {p["role"] for p in self.types[a["record_type"]]["permissions"] if p.get("read")}
            self.assertLessEqual(set(a["roles"]), readers)     # a press re-checks the user's read on the record
        subs = {s["key"]: s for s in self.m["extension_subscriptions"]}
        self.assertEqual(sorted(subs), ["link", "work"])
        self.assertEqual(sorted(self.m["allowed_urls"]), sorted(s["endpoint_url"] for s in subs.values()))
        self.assertEqual({s["endpoint_url"].split("/pst/")[0] for s in subs.values()}, {"https://host.docker.internal:8125"})

    def test_the_four_reports(self):
        r = {x["name"]: x for x in self.m["reports"]}
        self.assertEqual(sorted(r), ["PP PST Carts", "PP PST Production by worker", "PP PST Sell-through by colour", "PP PST Tags"])
        self.assertEqual({c.split(".")[0] for c in r["PP PST Production by worker"]["columns"] if "." in c}, {"worker_rows"})
        self.assertEqual({c.split(".")[0] for c in r["PP PST Sell-through by colour"]["columns"] if "." in c}, {"colour_rows"})
        for x in r.values():
            own = set(self.fields[x["ref_doctype"]]) | {"name"}
            self.assertTrue({c.split(".")[-1] for c in x["columns"]} <= own | set(self.fields["PP PST Worker Row"])
                            | set(self.fields["PP PST Colour Row"]), x["name"])

    def test_the_rights_the_service_needs_and_no_more(self):
        rights = {(e["doctype"], e["role"]): e["rights"] for e in self.m["role_rights"] if "doctype" in e}
        self.assertEqual(rights[("Stock Entry", INT)], ["read", "write", "create", "submit"])
        self.assertEqual([d for (d, r), x in rights.items() if r == INT and x == ["read"]],
                         ["Item", "Warehouse", "System Settings"])
        self.assertTrue(all(x == ["select"] for (d, r), x in rights.items()
                            if r == INT and d not in ("Item", "Warehouse", "System Settings", "Stock Entry", "POS Invoice")))
        self.assertEqual(rights[("POS Invoice", INT)], ["read", "report"])
        self.assertEqual([e["report"] for e in self.m["role_rights"] if "report" in e], ["POS Sale Report"])
        self.assertEqual({d for (d, r) in rights if r == MGR}, {"Warehouse", "Item Group", "Company"})
        self.assertIn("reads no customer and sends nothing elsewhere", self.m["description"])
        self.assertIn("Read and Report on POS Invoice", self.m["description"])
        self.assertFalse(any("delete" in x or "cancel" in x for x in rights.values()))

    def test_the_apps_role_writes_tags_and_carts_and_the_lead_keeps_the_rest(self):
        perms = {n: {p["role"]: p for p in d.get("permissions", [])} for n, d in self.types.items()}
        on = lambda p: sorted(k for k, v in p.items() if v == 1)  # noqa: E731
        self.assertEqual(on(perms["PP PST Tag"][INT]), ["create", "read", "write"])
        self.assertEqual(on(perms["PP PST Cart"][INT]), ["create", "read", "write"])
        self.assertEqual(on(perms["PP PST Settings"][INT]), ["read"])
        self.assertEqual(on(perms["PP PST Station"][INT]), ["read", "write"])
        self.assertEqual(on(perms["PP PST Report"][INT]), ["read", "write"])
        self.assertEqual(on(perms["PP PST Tag"][MGR]), ["export", "read", "report"])
        self.assertIn("write", on(perms["PP PST Cart"][MGR]))     # Pounds

    def test_the_links_words_say_who_may_use_it_and_what_stops_it(self):
        cf = {(f["dt"], f["fieldname"]): f for f in self.m["custom_fields"]}
        d = cf[("PP PST Station", "link")]["description"]
        self.assertIn("Anyone with it can tag and send carts at this station", d)
        self.assertIn("Changing the station's settings stops it until Make link is pressed again.", d)
        self.assertEqual(self.fields["PP PST Worker Row"]["per_hour"]["label"], "Pieces per active hour")

    def test_the_feed_registration_is_frozen(self):
        (f,) = self.m["registered_applications"]
        self.assertEqual(f, FEED)
        self.assertLessEqual(len(f["description"]), 140)

    def test_each_record_a_person_opens_has_its_help_address(self):
        ps = {p["doc_type"]: p["value"] for p in self.m["property_setters"] if p["property"] == "documentation"}
        self.assertEqual(ps, {f"PP PST {k}": f"https://developer.ivendnext.com/recipes/production_station.html#{a}"
                              for k, a in (("Settings", "settings"), ("Station", "stations"), ("Cart", "carts"),
                                           ("Report", "reports"), ("Tag", "tags"))})

    def test_the_english_words_cover_every_name_the_store_sees(self):   # Desk shows people's words, never the code
        names = {d["name"] for d in self.m["doctypes"]} | {x["name"] for x in self.m["reports"]}
        names |= {x["name"] for x in self.m["registered_applications"]}
        for d in self.m["doctypes"]:
            names |= {p["role"] for p in d.get("permissions", []) if not p["role"].endswith(" Integration")}
        (en,) = [t["words"] for t in self.m["translations"] if t["language"] == "en"]
        self.assertEqual(sorted(n for n in names if n.startswith(self.m["prefix"]) and n not in en), [])
        self.assertTrue(all(w and not w.startswith(self.m["prefix"]) for w in en.values()))


if __name__ == "__main__":
    unittest.main()
