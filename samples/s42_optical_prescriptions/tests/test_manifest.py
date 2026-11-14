"""S42's manifest passes the kit's checker; the check is on from the install and lets the sale go on when down; the
fields are the ones the service reads; the integration role only reads (the settings and the prescriptions); the
prescriptions are written by the optometrist and read by store staff; the lab order's workflow sets the two ticks the
report and the shop's own messages read; each record type opens its help."""
import json
import os
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parents[2] / "tools" / "manifest"), str(HERE.parent / "service"), str(HERE.parent)]
import validate  # noqa: E402

try:
    import jinja2
    from jinja2.sandbox import SandboxedEnvironment
except ImportError:
    if os.environ.get("S42_REQUIRE_JINJA"):
        raise
    jinja2 = None

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
P = MANIFEST["prefix"]
DT = {d["name"]: d for d in MANIFEST["doctypes"]}
(SUB,) = MANIFEST["extension_subscriptions"]
PF = {p["name"]: p for p in MANIFEST["print_formats"]}


class Doc(dict):
    """A record as a print format reads it: fields as attributes, and get_formatted as the engine's own, which drops a
    whole number's decimals on a Float field with no options (-1.0 prints -1: the walk's sheet on demo-optical)."""
    __getattr__ = dict.get

    def get_formatted(self, field):
        v = self.get(field)
        return ("%f" % v).rstrip("0").rstrip(".") if isinstance(v, float) else ("" if v is None else str(v))


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

    @unittest.skipUnless(jinja2, "jinja2 is not installed: the job sheet's rendering test did not run")
    def test_the_job_sheet_prints_each_lens_value_in_its_fields_format(self):     # run 11's walk: -0.5; F-OP-7: -1
        pf = PF[f"{P} Job Sheet"]
        for side in ("r", "l"):
            for f in ("sph", "cyl", "add"):
                self.assertIn(f"{{{{ power(doc.{side}_{f}) }}}}", pf["html"])
            self.assertIn(f"{{{{ amount(doc.{side}_prism) }}}}", pf["html"])
        doc = Doc(name="OPT-LAB-00023", customer_name="Ingrid Solberg", prescription="RX-00028", due_date="2026-11-21",
                  r_sph=-1.25, r_cyl=-0.5, r_axis=90, r_add=2.0, r_prism=0.0, l_sph=-1.0, l_cyl=-0.25, l_axis=85,
                  l_add=2.0, l_prism=0.0, pd_distance=63.0, pd_near=60.0, r_height=22.0, l_height=22.0, store_name="SoHo")
        out = SandboxedEnvironment(autoescape=True).from_string(pf["html"]).render(doc=doc, _=lambda t: t)
        text = " ".join(re.sub(r"<[^>]+>", " ", out).split())
        self.assertIn("Right eye -1.25 -0.50 90 +2.00 0.00", text)      # what the lab reads
        self.assertIn("Left eye -1.00 -0.25 85 +2.00 0.00", text)       # a whole power, -1.00 not -1
        self.assertIn("Collect at SoHo", text)

    def test_the_job_sheet_prints_the_stores_own_name_and_names_the_eyes(self):
        pf = PF[f"{P} Job Sheet"]
        self.assertEqual(fields(f"{P} Lab Order")["store_name"]["fetch_from"], "store.warehouse_name")
        self.assertIn('{{ doc.store_name or doc.store or "" }}', pf["html"])
        for bare in ('_("Right")', '_("Left")'):      # the shared language files read a bare Right or Left as a right, to leave
            self.assertNotIn(bare, pf["html"])

    def test_the_prescription_prints_on_its_own_sheet_by_default_with_each_eye_named(self):   # F-OP-7: the plain layout
        pf = PF[f"{P} Prescription Sheet"]
        self.assertEqual((pf["doc_type"], pf["print_format_type"]), (f"{P} Prescription", "Jinja"))
        default = {ps["doc_type"]: ps["value"] for ps in MANIFEST["property_setters"] if ps["property"] == "default_print_format"}
        self.assertEqual(default, {f"{P} Lab Order": f"{P} Job Sheet", f"{P} Prescription": f"{P} Prescription Sheet"})
        html, rx = pf["html"], fields(f"{P} Prescription")
        for side in ("r", "l"):                     # each power signed to two places, the prism to two, the axis whole
            for f in ("sph", "cyl", "add"):
                self.assertIn(f"{{{{ power(doc.{side}_{f}) }}}}", html)
            self.assertIn(f"{{{{ amount(doc.{side}_prism) }}}}", html)
            self.assertIn(f"{{{{ (doc.{side}_axis or 0)|int }}}}", html)
            for f in ("sph", "cyl", "add", "prism", "bc", "dia", "axis"):
                self.assertIn(f"{side}_{f}", rx)
                self.assertNotIn(f"{{{{ doc.{side}_{f} }}}}", html)
        self.assertEqual(html.count('_("Right eye")'), 2)
        self.assertEqual(html.count('_("Left eye")'), 2)
        for bare in ('_("Right")', '_("Left")'):
            self.assertNotIn(bare, html)
        self.assertIn('<div dir="auto"', html)
        # a contact lens's base curve and diameter print only on a contact-lens prescription, never as 0 on spectacles
        self.assertIn("Contact lenses", rx["kind"]["options"].split("\n"))
        (block,) = re.findall(r"\{%-? *if (.*?) *-?%\}(.*?)\{%-? *endif *-?%\}", html, re.S)
        self.assertEqual(block[0], 'doc.kind == "Contact lenses"')
        for f in ("r_bc", "r_dia", "l_bc", "l_dia", "cl_lens"):
            self.assertIn(f"doc.{f}" if f == "cl_lens" else f'get_formatted("{f}")', block[1], f)
            self.assertNotIn(f, html.replace(block[1], ""), f)          # nowhere outside the contact-lens block
        for f in ("examined_by", "registration", "notes"):              # who examined, under which registration
            self.assertIn(f"{{{{ doc.{f} or \"\" }}}}", html.replace(block[1], ""), f)

    @unittest.skipUnless(jinja2, "jinja2 is not installed: the prescription sheet's rendering test did not run")
    def test_the_prescription_sheet_prints_the_walks_prescription_as_an_optometrist_writes_it(self):  # F-OP-7, demo-optical
        def sheet(**values):
            doc = Doc(name="RX-00028", customer_name="Ingrid Solberg", kind="Spectacles", test_date="2026-11-14",
                      valid_until="2028-11-14", r_sph=-1.25, r_cyl=-0.5, r_axis=90, r_add=0.0, r_prism=0.0,
                      l_sph=-1.0, l_cyl=-0.25, l_axis=85, l_add=0.0, l_prism=0.0, pd_distance=63.0, pd_near=0.0,
                      r_bc=0.0, r_dia=0.0, l_bc=0.0, l_dia=0.0, examined_by="Dr. Castellanos", registration="NY-0042")
            doc.update(values)
            env = SandboxedEnvironment(autoescape=True)
            out = env.from_string(PF[f"{P} Prescription Sheet"]["html"]).render(doc=doc, _=lambda t: t)
            return " ".join(re.sub(r"<[^>]+>", " ", out).split())
        text = sheet()
        self.assertIn("Prescription RX-00028", text)                    # its own name, never the record type's
        self.assertNotIn(P, text)
        self.assertIn("Right eye -1.25 -0.50 90 0.00 0.00", text)
        self.assertIn("Left eye -1.00 -0.25 85 0.00 0.00", text)        # the walk's -1 and 0
        self.assertIn("Distance PD 63 mm", text)
        self.assertNotIn("Base curve", text)                            # spectacles: no contact-lens values at 0
        self.assertIn("Examined by Dr. Castellanos · Registration number NY-0042", text)
        text = sheet(r_sph=1.5, r_add=2.0, l_sph=0.0, l_add=2.25, l_prism=1.0, l_base="In")
        self.assertIn("Right eye +1.50 -0.50 90 +2.00 0.00", text)      # a plus sign on a positive power
        self.assertIn("Left eye 0.00 -0.25 85 +2.25 1.00 In", text)     # a prism is an amount: its direction is Base
        text = sheet(kind="Contact lenses", r_bc=8.6, l_bc=8.6, r_dia=14.2, l_dia=14.2, cl_lens="Daily toric")
        self.assertIn("Right eye 8.6 14.2", text)
        self.assertIn("Lens brand and type Daily toric", text)

    def test_desk_names_the_records_states_and_buttons_in_plain_words(self):
        (tr,) = MANIFEST["translations"]
        self.assertEqual(tr["language"], "en")
        (wf,) = MANIFEST["workflows"]
        named = ({d["name"] for d in MANIFEST["doctypes"]} | {s["state"] for s in wf["states"]}
                 | {t["action"] for t in wf["transitions"]} | {r["name"] for r in MANIFEST["reports"]} | set(PF))
        self.assertEqual(set(tr["words"]), named)
        self.assertEqual(tr["words"][f"{P} Prescription"], "Prescription")
        self.assertEqual(tr["words"][f"{P} Lab Order"], "Lab order")
        self.assertFalse([w for w in tr["words"].values() if P in w])

    def test_no_notification_or_address_reaches_a_customer_from_the_manifest(self):
        self.assertNotIn("notifications", MANIFEST)        # the shop's own Notifications do (the guide)

    def test_each_record_type_opens_its_help(self):
        got = {ps["doc_type"]: ps["value"] for ps in MANIFEST["property_setters"] if ps["property"] == "documentation"}
        self.assertEqual(set(got), {f"{P} Prescription", f"{P} Lab Order", f"{P} Settings"})
        for v in got.values():
            self.assertTrue(v.startswith("https://") and "#" in v)


if __name__ == "__main__":
    unittest.main()
