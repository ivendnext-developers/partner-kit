"""S62's manifest: the duty class, the return and its lines; the three Item fields; a workflow whose File step only the
Stock Manager takes; a lock on a filed return covering every figure and what they were worked out from, the filing date
and reference left for the manager; one button on a draft return sending only its name; nobody but a System Manager
deletes a return; the print grouping the lines by class; the address the service's.

    python3 -m unittest discover -s samples/s62_liquor_excise_returns/tests -p 'test_*.py'
"""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.dirname(os.path.dirname(ROOT))
MANIFEST = os.path.join(ROOT, "manifest.json")
P, INT = "PP EXR", "PP EXR Integration"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.types = {d["name"]: d for d in self.m["doctypes"]}
        self.ret = {f["fieldname"]: f for f in self.types[f"{P} Return"]["fields"]}
        self.line = {f["fieldname"]: f for f in self.types[f"{P} Return Line"]["fields"]}

    def test_the_kits_checker_and_the_sites_install_rules_pass_it(self):
        for tool in ("tools/manifest/validate.py", "tools/manifest/site_rules.py"):
            r = subprocess.run([sys.executable, os.path.join(KIT, tool), MANIFEST], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, tool + r.stdout + r.stderr)

    def test_a_duty_class_a_return_and_its_lines(self):
        self.assertEqual(sorted(self.types), [f"{P} Duty Class", f"{P} Return", f"{P} Return Line"])
        self.assertEqual(self.ret["lines"]["options"], f"{P} Return Line")
        self.assertEqual(self.line["duty_class"]["options"], f"{P} Duty Class")
        self.assertEqual((self.types[f"{P} Return"]["autoname"], self.types[f"{P} Duty Class"]["autoname"]),
                         ("format:EXR-R-{#####}", "field:class_name"))

    def test_the_lines_and_who_worked_them_out_are_the_services_alone(self):
        for f in self.line.values():
            self.assertEqual(f.get("read_only"), 1, f["fieldname"])
        for f in ("lines", "summary", "worked_out_by", "worked_out_at"):
            self.assertEqual(self.ret[f].get("read_only"), 1, f)
        for f in ("units", "volume", "pure_alcohol"):
            self.assertEqual((self.line[f]["fieldtype"], self.line[f].get("precision")), ("Float", "3"), f)

    def test_only_the_stock_manager_files_a_return(self):
        wf = self.m["workflows"][0]
        self.assertEqual([(t["state"], t["next_state"], t["allowed"]) for t in wf["transitions"]],
                         [(f"{P} Draft", f"{P} Filed", "Stock Manager")])
        self.assertEqual({s["state"]: s["allow_edit"] for s in wf["states"]},
                         {f"{P} Draft": "Stock User", f"{P} Filed": "Stock Manager"})

    def test_a_filed_return_is_locked_on_every_figure_and_its_source_but_not_the_filing(self):
        rule = self.m["save_rules"][0]
        self.assertEqual((rule["kind"], rule["mode"], rule["states"]), ("locked_in_state", "refuse", [f"{P} Filed"]))
        self.assertEqual(set(rule["locked_fields"]), {"company", "store", "unit", "from_date", "to_date", "lines",
                                                      "summary", "worked_out_by", "worked_out_at"})
        self.assertNotIn("filed_on", rule["locked_fields"])
        self.assertEqual((self.ret["company"].get("set_only_once"), self.ret["store"].get("set_only_once")), (1, 1))

    def test_the_button_is_on_a_draft_return_and_sends_only_its_name(self):
        (a,) = self.m["desk_actions"]
        self.assertEqual((a["label"], a["service"], a["roles"], a["record_type"], a["placement"], a["send_fields"]),
                         ("Work out the return", "work", ["Stock User", "Stock Manager"], f"{P} Return", "form", "name"))
        self.assertEqual(a["conditions"], [{"field": "workflow_state", "operator": "=", "value": f"{P} Draft"}])
        self.assertLessEqual(len(a["confirm_text"]), 140)

    def test_nobody_but_a_system_manager_deletes_and_the_apps_role_reads_and_writes_returns_only(self):
        perms = {p["role"]: p for p in self.types[f"{P} Return"]["permissions"]}
        self.assertEqual(sorted(r for r, p in perms.items() if p["delete"]), ["System Manager"])
        self.assertEqual(sorted(k for k, v in perms[INT].items() if v == 1), ["read", "write"])
        cls = {p["role"]: p for p in self.types[f"{P} Duty Class"]["permissions"]}
        self.assertEqual(sorted(k for k, v in cls[INT].items() if v == 1), ["read"])

    def test_the_item_fields_name_the_class_the_millilitres_and_the_strength(self):
        f = {c["fieldname"]: c for c in self.m["custom_fields"]}
        self.assertEqual({k: (v["dt"], v["fieldtype"]) for k, v in f.items()},
                         {"pp_exr_class": ("Item", "Link"), "pp_exr_ml": ("Item", "Float"), "pp_exr_abv": ("Item", "Percent")})
        self.assertEqual(f["pp_exr_class"]["options"], f"{P} Duty Class")

    def test_the_print_groups_the_lines_by_class_under_the_letter_head(self):
        (pf,) = self.m["print_formats"]
        html = pf["html"]
        self.assertEqual((pf["doc_type"], pf["print_format_type"]), (f"{P} Return", "Jinja"))
        for want in ('groupby("duty_class")', "{% if letter_head and not no_letterhead %}", 'state.endswith(" Filed")',
                     'r.get_formatted("pure_alcohol")', 'dir="auto"'):
            self.assertIn(want, html)

    def test_the_address_is_the_services_and_the_feed_says_leave_it_off(self):
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"] for s in self.m["extension_subscriptions"]])
        (s,) = self.m["extension_subscriptions"]
        self.assertEqual((s["key"], s["point"], s["timeout_seconds"]), ("work", "desk_action", 10))
        (reg,) = self.m["registered_applications"]
        self.assertLessEqual(len(reg["description"]), 140)
        self.assertIn("leave the feed off", reg["description"])


if __name__ == "__main__":
    unittest.main()
