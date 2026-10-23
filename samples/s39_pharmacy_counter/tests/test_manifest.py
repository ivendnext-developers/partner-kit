"""S39's manifest passes the kit's checker; five services install switched off with the down answers the design names
(the dispensary refuses, the front lets the sale through, the Desk refuses); the two till checks fit one POS Profile's
10 seconds beside the age check; the record types, fields and sale details are the ones the service reads; only the
pharmacist-in-charge writes the Pharmacist list, only pharmacists write prescriptions, only the service writes dispensings;
nothing is required and nothing names a role the framework gives by itself."""
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
SUBS = {s["key"]: s for s in MANIFEST["extension_subscriptions"]}
P, PF = MANIFEST["prefix"], MANIFEST["app"]
DT = {d["name"]: d for d in MANIFEST["doctypes"]}


def perm(dt, role):
    row = next((p for p in DT[dt]["permissions"] if p["role"] == role), None)
    return {k for k, v in (row or {}).items() if k != "role" and v}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_five_services_switched_off_with_the_designs_down_answers(self):
        self.assertEqual({k: (s["point"], s["down_answer"]) for k, s in SUBS.items()},
                         {"dispensary": ("check", "refuse"), "front": ("check", "allow_and_flag"),
                          "desk_order": ("doccheck", "refuse"), "desk_delivery": ("doccheck", "refuse"),
                          "desk_invoice": ("doccheck", "refuse")})
        for s in SUBS.values():
            self.assertFalse(any(k in s for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))

    def test_the_two_till_checks_fit_one_profiles_ten_seconds_beside_the_age_check(self):
        disp, front = SUBS["dispensary"]["timeout_seconds"], SUBS["front"]["timeout_seconds"]
        self.assertLessEqual(disp + front, 10)              # the shop's checker counts them as one profile
        self.assertLessEqual(max(disp, front) + 4, 10)      # S37's library copy takes 4 s on the same profile

    def test_the_desk_checks_name_their_record_types_send_stock_qty_and_never_a_draft(self):
        for key, dt in (("desk_order", "Sales Order"), ("desk_delivery", "Delivery Note"), ("desk_invoice", "Sales Invoice")):
            st = SUBS[key]["settings"]
            self.assertEqual((st["record_type"], st["on_validate"]), (dt, False))
            self.assertIn("stock_qty", st["send_fields"])
            self.assertIn(f"{PF}_rx_number", st["send_fields"])
        self.assertIn("against_sales_order", SUBS["desk_delivery"]["settings"]["send_fields"])
        self.assertIn("delivery_note", SUBS["desk_invoice"]["settings"]["send_fields"])

    def test_the_routes_are_the_services_own_and_its_only_addresses_on_one_origin(self):
        import app
        for key, s in SUBS.items():
            path = "/" + s["endpoint_url"].split("/", 3)[3]
            self.assertEqual(app.ROUTES[path][0], key)
        self.assertEqual(sorted(MANIFEST["allowed_urls"]), sorted(s["endpoint_url"] for s in SUBS.values()))
        self.assertEqual(len({u.split("/")[2] for u in MANIFEST["allowed_urls"]}), 1)

    def test_the_sale_details_are_the_ones_the_service_reads_and_never_required(self):
        import rxrules
        want = [f"{P} {s}" for s in (rxrules.RX, rxrules.PRESCRIBER, rxrules.LICENCE, rxrules.DIRECTIONS)]
        self.assertEqual([a for a in MANIFEST["sale_attributes"]], [{"name": n} for n in want])

    def test_the_desk_fields_are_the_ones_the_service_reads_on_each_document(self):
        import rxrules
        for dt in rxrules.DESK_TYPES:
            got = {f["fieldname"] for f in MANIFEST["custom_fields"] if f["dt"] == dt}
            self.assertEqual(got, {f"{PF}_{v}" for v in rxrules.DESK_FIELDS.values()})
        cust = {f["fieldname"]: f["fieldtype"] for f in MANIFEST["custom_fields"] if f["dt"] == "Customer"}
        self.assertEqual(cust[f"{PF}_consent_date"], "Date")       # 0.1.1's types, unchanged: an update may not change one
        self.assertFalse([f for f in MANIFEST["custom_fields"] if f.get("reqd")])

    def test_the_patient_record_holds_every_field_a_schedule_may_need_and_only_the_pharmacists_read_it(self):
        # 0.1.2 (PH-B1d): a record of its own, so the framework's paths that pass a permission level by (the form's
        # change history, the group-by count, the link search) answer only those who read the record at all
        import rxrules
        pat = DT[f"{P} Patient"]
        fields = {f["fieldname"]: f for f in pat["fields"]}
        self.assertTrue({f for _, f, _ in rxrules.IDENTITY} | {"consent_by"} <= set(fields))
        self.assertEqual(fields["consent_date"]["fieldtype"], "Date")
        self.assertIn("parent or guardian", fields["consent_date"]["description"])
        cust = fields["customer"]
        self.assertEqual((cust["fieldtype"], cust["options"], cust.get("reqd"), cust.get("unique")), ("Link", "Customer", 1, 1))
        # named by a hash, never after its customer: the group-by count's assignment branch matches a name, not a type
        self.assertEqual(pat["autoname"], "hash")
        self.assertEqual(pat.get("track_changes"), 1)
        self.assertNotIn("search_fields", pat)
        readers = {p["role"]: {k for k, v in p.items() if v == 1} for p in pat["permissions"]}
        self.assertEqual({r for r, k in readers.items() if k}, {f"{P} Pharmacist", f"{P} Pharmacist in Charge",
                                                               f"{P} Integration", f"{P} Records Officer"})
        # the shop's installer gives System Manager every right on a record type whose manifest names no System Manager
        # row (measured, PH-B1d run 1): a row with none keeps the site's administrator out of the patients by default
        self.assertEqual(readers.get("System Manager"), set())
        self.assertEqual(readers[f"{P} Integration"], {"read"})
        self.assertEqual({r for r, k in readers.items() if "delete" in k}, {f"{P} Records Officer"})
        self.assertFalse([r for r, k in readers.items() if k & {"export", "print", "email", "share"}])
        # no Connections link to it: a count there would tell any customer reader the person is a patient
        self.assertFalse([ln for ln in MANIFEST["links"] if ln["link_doctype"] == f"{P} Patient"])

    def test_the_customer_fields_of_0_1_1_stay_empty_and_show_only_while_they_hold_a_value(self):
        # an update may not drop a field (recipes/manifest.md step 6): they stay, shown only until the shop moves them
        cust = {f["fieldname"]: f for f in MANIFEST["custom_fields"] if f["dt"] == "Customer"}
        self.assertEqual(set(cust), {f"{PF}_{f}" for f in ("id_number", "birth_date", "authority", "consent_date", "consent_by")})
        for name, f in cust.items():
            self.assertEqual(f.get("depends_on"), name, name)
            self.assertIn("Not used since version 0.1.2", f["description"], name)
            self.assertTrue(f["label"].endswith("(moved)"), name)
        self.assertFalse([f for f in MANIFEST["custom_fields"] if "permlevel" in f])

    def test_the_schedule_holds_every_rule_the_service_reads(self):
        import rxrules
        fields = {f["fieldname"] for f in DT[f"{P} Drug Schedule"]["fields"]}
        for k in ("needs_prescription", "pharmacist_only", "dispensary_only", "validity_days", "max_fills", "qty_cap",
                  "freq_qty", "freq_days", "returnable", "return_gives_back", "needs_directions", "axis",
                  "own_sale_without_rx"):
            self.assertIn(k, fields)
        self.assertTrue({t for t, _, _ in rxrules.IDENTITY} <= fields)
        self.assertIn("needs_consent", fields)

    def test_who_writes_what(self):
        self.assertEqual(perm(f"{P} Pharmacist", "System Manager") & {"write", "create", "delete"}, set())
        self.assertIn("write", perm(f"{P} Pharmacist", f"{P} Pharmacist in Charge"))
        self.assertEqual(perm(f"{P} Pharmacist", f"{P} Pharmacist") & {"write", "create"}, set())
        self.assertEqual(perm(f"{P} Prescription", f"{P} Integration"), {"read"})
        self.assertIn("create", perm(f"{P} Prescription", f"{P} Pharmacist"))
        self.assertEqual(perm(f"{P} Prescription", "System Manager") & {"write", "create"}, set())
        self.assertEqual(perm(f"{P} Dispensing", f"{P} Integration"), {"read", "write", "create"})
        for role in ("System Manager", f"{P} Pharmacist"):
            self.assertEqual(perm(f"{P} Dispensing", role) & {"write", "create", "delete"}, set())
        # the pharmacist-in-charge may release a stuck reservation by hand, never make or delete one
        self.assertEqual(perm(f"{P} Dispensing", f"{P} Pharmacist in Charge") & {"write", "create", "delete"}, {"write"})

    def test_only_the_records_officer_destroys_a_prescription_or_a_dispensing(self):
        # a law keeps a prescription for years (AE 25, SA 3 and its register 5, GH 2, KE 2 if not repeatable): a permission
        # row is role-wide, so no role that works the counter may delete one; the shop gives the officer's role for the act,
        # and the officer deletes the patient's record too when the last of their periods ends
        officer = f"{P} Records Officer"
        for dt in (f"{P} Prescription", f"{P} Dispensing"):
            deleters = {p["role"] for p in DT[dt]["permissions"] if p.get("delete")}
            self.assertEqual(deleters, {officer}, dt)
            self.assertEqual(perm(dt, officer), {"read", "report", "delete"}, dt)
        self.assertEqual(perm(f"{P} Patient", officer), {"read", "report", "delete"})
        for d in MANIFEST["doctypes"]:
            if d["name"] not in (f"{P} Prescription", f"{P} Dispensing", f"{P} Patient"):
                self.assertFalse([p for p in d.get("permissions") or [] if p["role"] == officer], d["name"])
        self.assertEqual(perm(f"{P} Prescription", f"{P} Pharmacist in Charge") & {"delete"}, set())

    def test_the_prescription_image_is_said_to_be_private_on_the_desk(self):
        img = next(f for f in DT[f"{P} Prescription"]["fields"] if f["fieldname"] == "image")
        self.assertEqual(img["fieldtype"], "Attach")
        self.assertNotIn("make_attachment_public", img)      # the field's own setting: private when attached on the Desk
        self.assertNotIn("make_attachments_public", DT[f"{P} Prescription"])
        self.assertIn("Private when attached on the Desk", img["description"])

    def test_no_market_in_the_apps_code_or_names(self):
        # a market's rules are its schedules, records the shop loads (README step 4): never a name in code. Its words to a
        # reader may give examples. The trade's own words (Drug Schedule, Pharmacist) are this app's, so only markets are barred
        import tokenize
        names_re = re.compile(r"kenya|nigeria|ghana|egypt|saudi|emirat|dubai|abu_?dhabi|jordan|mexic|nairobi|lagos|accra|"
                              r"cairo|riyadh|amman|sfda|nafdac|mohap|cofepris|tatmeen|nphies|jfda", re.I)
        codes = {"ke", "ng", "gh", "eg", "sa", "ae", "uae", "jo", "mx", "ksa", "dha", "doh", "eda", "ppb", "nhia", "pdpl"}

        def market(n):  # a market's name anywhere in a name, or its code as one part of it (KE_DAYS, pp_rxc_sa_id)
            return names_re.search(n) or any(x.lower() in codes for x in re.split(r"[_\s-]+", n))
        code_word = re.compile(r"\b(KE|NG|GH|EG|SA|AE|UAE|JO|MX|KSA)\b")      # a market's code as a value the code compares
        for py in ("rxrules.py", "service/app.py"):
            with open(HERE.parent / py, encoding="utf-8") as f:
                toks = list(tokenize.generate_tokens(f.readline))
            idents = [t.string for t in toks if t.type == tokenize.NAME]
            self.assertFalse([i for i in idents if market(i)], py)
            # the strings the code holds, its docstrings left out (words to a reader may give examples)
            strings = [t.string for t in toks if t.type == tokenize.STRING and not t.string.startswith(('"""', 'r"""'))]
            self.assertFalse([x for x in strings if code_word.search(x) or names_re.search(x)], py)
        names = [MANIFEST["app"], MANIFEST["prefix"], MANIFEST["title"]] + [d["name"] for d in MANIFEST["doctypes"]] + \
                [f["fieldname"] for d in MANIFEST["doctypes"] for f in d["fields"]] + \
                [p["role"] for d in MANIFEST["doctypes"] for p in d.get("permissions") or []] + \
                [f["fieldname"] for f in MANIFEST["custom_fields"]] + [a["name"] for a in MANIFEST["sale_attributes"]]
        self.assertFalse([n for n in names if market(n)], names)

    def test_the_dispensing_is_named_by_the_services_key_and_every_record_keeps_its_changes(self):
        self.assertEqual(DT[f"{P} Dispensing"]["autoname"], "field:key")
        for d in MANIFEST["doctypes"]:
            if not d.get("istable"):
                self.assertEqual(d.get("track_changes"), 1, d["name"])

    def test_the_licence_reminders_go_to_the_pharmacist_in_charge(self):
        n = {x["document_type"]: x for x in MANIFEST["notifications"]}
        for dt in (f"{P} Pharmacist", f"{P} Premises Licence"):
            self.assertEqual((n[dt]["event"], n[dt]["date_changed"]), ("Days Before", "valid_until"))
            self.assertEqual(n[dt]["recipients"], [{"receiver_by_role": f"{P} Pharmacist in Charge"}])

    def test_each_record_type_opens_its_help(self):
        own = {d["name"] for d in MANIFEST["doctypes"] if not d.get("istable")}
        got = {p["doc_type"] for p in MANIFEST["property_setters"] if p["property"] == "documentation"}
        self.assertEqual(got, own - {f"{P} Prescription Item", f"{P} Item Schedule"})


if __name__ == "__main__":
    unittest.main()
