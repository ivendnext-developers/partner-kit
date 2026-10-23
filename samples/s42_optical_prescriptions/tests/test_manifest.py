"""S42's manifest passes the kit's checker; the check installs switched off and lets the sale go on when down; the
fields are the ones the service reads; the integration role only reads (the settings and the prescriptions); the
prescriptions are written by the optometrist and read by store staff; the lab order's workflow sets the two ticks the
report and the shop's own messages read; each record type opens its help."""
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
P = MANIFEST["prefix"]
DT = {d["name"]: d for d in MANIFEST["doctypes"]}
(SUB,) = MANIFEST["extension_subscriptions"]


def fields(dt):
    return {f["fieldname"]: f for f in DT[dt]["fields"]}


def rights(dt, role):
    row = next(p for p in DT[dt]["permissions"] if p["role"] == role)
    return {k for k, v in row.items() if k != "role" and v}


class ManifestTest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_one_check_switched_off_that_lets_the_sale_go_on_when_down(self):
        self.assertEqual((SUB["key"], SUB["point"], SUB["down_answer"]), ("check", "check", "allow_and_flag"))
        self.assertFalse(any(k in SUB for k in ("enabled", "consent_given", "scope", "secret", "may_approve")))
        self.assertLessEqual(SUB["timeout_seconds"], 10)

    def test_the_route_is_the_services_own_and_its_only_address(self):
        import app
        path = "/" + SUB["endpoint_url"].split("/", 3)[3]
        self.assertEqual(app.ROUTES[path], SUB["key"])
        self.assertEqual(MANIFEST["allowed_urls"], [SUB["endpoint_url"]])

    def test_the_marks_are_the_ones_the_service_reads(self):
        import optical
        f = optical.field_of(P)
        got = {(c["dt"], c["fieldname"], c["fieldtype"], c["options"]) for c in MANIFEST["custom_fields"]}
        marks = "\n" + "\n".join((*optical.KINDS, optical.NOT_NEEDED))
        self.assertEqual(got, {("Item Group", f, "Select", marks), ("Item", f, "Select", marks)})

    def test_a_prescription_requires_what_the_service_reads_and_holds_its_kinds(self):
        import optical
        rx = fields(f"{P} Prescription")
        self.assertEqual(tuple(rx["kind"]["options"].split("\n")), optical.KINDS)
        for k in ("customer", "kind", "test_date", "valid_until"):
            self.assertEqual(rx[k].get("reqd"), 1, k)
        self.assertEqual(rx["customer"]["options"], "Customer")

    def test_the_settings_record_holds_what_the_service_reads(self):
        d = DT[f"{P} Settings"]
        self.assertEqual(d["autoname"], "field:title")
        self.assertEqual({f["fieldname"] for f in d["fields"]}, {"title", "hours_from_utc"})

    def test_the_integration_role_only_reads(self):
        role = f"{P} Integration"            # so the install makes it (the product's install rule)
        self.assertEqual(rights(f"{P} Settings", role), {"read"})
        self.assertEqual(rights(f"{P} Prescription", role), {"read"})
        self.assertNotIn(role, {p["role"] for p in DT[f"{P} Lab Order"]["permissions"]})

    def test_the_optometrist_writes_prescriptions_and_store_staff_read_them(self):
        self.assertTrue({"read", "write", "create"} <= rights(f"{P} Prescription", f"{P} Optometrist"))
        self.assertEqual(rights(f"{P} Prescription", "Sales User"), {"read", "report", "print"})
        self.assertTrue({"read", "write", "create"} <= rights(f"{P} Lab Order", "Sales User"))
        self.assertEqual(rights(f"{P} Lab Order", f"{P} Optometrist"), {"read", "report", "print"})  # the buttons are Sales User's
        self.assertNotIn("delete", rights(f"{P} Lab Order", "Sales User"))

    def test_a_lab_order_copies_its_prescription_read_only(self):
        lab, rx = fields(f"{P} Lab Order"), fields(f"{P} Prescription")
        self.assertEqual(lab["prescription"]["options"], f"{P} Prescription")
        copied = {n: f for n, f in lab.items() if (f.get("fetch_from") or "").startswith("prescription.")}
        self.assertTrue({"customer", "customer_name", "customer_email", "kind", "r_sph", "l_sph", "pd_distance"} <= set(copied))
        for n, f in copied.items():
            self.assertEqual(f.get("read_only"), 1, n)
            self.assertIn(f["fetch_from"].split(".", 1)[1], rx, n)          # it names a field the prescription has

    def test_the_workflow_ticks_ready_at_the_store_unticks_it_on_a_remake_and_closes_at_the_end(self):
        (wf,) = MANIFEST["workflows"]
        sets = {s["state"][len(P) + 1:]: (s.get("update_field"), s.get("update_value")) for s in wf["states"]}
        self.assertEqual(sets, {"Ordered": (None, None), "Sent to lab": ("ready_to_collect", "0"),
                                "Ready to collect": ("ready_to_collect", "1"), "Collected": ("closed", "1"),
                                "Cancelled": ("closed", "1")})
        self.assertTrue(all(t["allow_self_approval"] == 1 for t in wf["transitions"]))   # whoever made the order moves it
        moves = {(t["state"][len(P) + 1:], t["next_state"][len(P) + 1:]) for t in wf["transitions"]}
        self.assertTrue({("Ready to collect", "Sent to lab"), ("Ready to collect", "Cancelled"),
                         ("Ordered", "Cancelled"), ("Sent to lab", "Cancelled")} <= moves)   # a remake; an order never collected
        self.assertEqual({t["allowed"] for t in wf["transitions"]} | {s["allow_edit"] for s in wf["states"][:3]}, {"Sales User"})
        (rep,) = MANIFEST["reports"]
        self.assertEqual(rep["filters"], [["closed", "=", 0]])
        # Desk puts a saved filter on a standard-filter field into that field, and an unticked Check filters nothing
        # (run 11's walk: the report listed a collected order), so a field the report filters on is no standard filter
        lab = fields(f"{P} Lab Order")
        self.assertFalse(any(lab[f].get("in_standard_filter") for f, _op, _v in rep["filters"]))
        for f in ("ready_to_collect", "closed"):
            self.assertEqual(fields(f"{P} Lab Order")[f]["read_only"], 1)

    def test_the_job_sheet_prints_each_lens_value_in_its_fields_format(self):     # run 11's walk: -0.5, not -0.50
        (pf,) = MANIFEST["print_formats"]
        for side in ("r", "l"):
            for f in ("sph", "cyl", "add", "prism"):
                self.assertIn(f'doc.get_formatted("{side}_{f}")', pf["html"])
                self.assertNotIn(f"{{{{ doc.{side}_{f} }}}}", pf["html"])

    def test_no_notification_or_address_reaches_a_customer_from_the_manifest(self):
        self.assertNotIn("notifications", MANIFEST)        # the shop's own Notifications do (the guide)

    def test_each_record_type_opens_its_help(self):
        got = {ps["doc_type"]: ps["value"] for ps in MANIFEST["property_setters"] if ps["property"] == "documentation"}
        self.assertEqual(set(got), {f"{P} Prescription", f"{P} Lab Order", f"{P} Settings"})
        for v in got.values():
            self.assertTrue(v.startswith("https://") and "#" in v)


if __name__ == "__main__":
    unittest.main()
