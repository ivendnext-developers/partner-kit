"""S61's manifest: the consignor, the payout and its lines; the two Item fields; a workflow whose move to Paid only the
app's own role takes; a lock on a paid or cancelled payout covering every field the payout's money rests on; two buttons
on a draft payout sending only its name; nobody but a System Manager deletes a payout; the addresses the service's.

    python3 -m unittest discover -s samples/s61_consignment_payouts/tests -p 'test_*.py'
"""

import json
import os
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.dirname(os.path.dirname(ROOT))
MANIFEST = os.path.join(ROOT, "manifest.json")
P, INT = "PP CSG", "PP CSG Integration"


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)
        self.types = {d["name"]: d for d in self.m["doctypes"]}
        self.pay = {f["fieldname"]: f for f in self.types[f"{P} Payout"]["fields"]}
        self.line = {f["fieldname"]: f for f in self.types[f"{P} Payout Line"]["fields"]}

    def test_the_kits_checker_and_the_sites_install_rules_pass_it(self):
        for tool in ("tools/manifest/validate.py", "tools/manifest/site_rules.py"):
            r = subprocess.run([sys.executable, os.path.join(KIT, tool), MANIFEST], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, tool + r.stdout + r.stderr)

    def test_a_consignor_a_payout_and_its_lines(self):
        self.assertEqual(sorted(self.types), [f"{P} Consignor", f"{P} Payout", f"{P} Payout Line"])
        self.assertEqual(self.pay["lines"]["options"], f"{P} Payout Line")
        self.assertEqual(self.pay["consignor"]["options"], f"{P} Consignor")

    def test_the_lines_and_totals_are_the_services_alone(self):
        for f in self.line.values():
            self.assertEqual(f.get("read_only"), 1, f["fieldname"])
        for f in ("lines", "sales_total", "payout_total", "summary", "worked_out_by", "paid_by", "consignor_name",
                  "currency"):
            self.assertEqual(self.pay[f].get("read_only"), 1, f)

    def test_only_the_apps_role_moves_a_payout_to_paid(self):
        wf = self.m["workflows"][0]
        to_paid = [t for t in wf["transitions"] if t["next_state"] == f"{P} Paid"]
        self.assertEqual([(t["state"], t["allowed"]) for t in to_paid], [(f"{P} Draft", INT)])
        self.assertEqual(sorted((t["state"], t["next_state"], t["allowed"]) for t in wf["transitions"]),
                         [(f"{P} Draft", f"{P} Cancelled", "Accounts User"), (f"{P} Draft", f"{P} Paid", INT),
                          (f"{P} Paid", f"{P} Cancelled", "Accounts Manager")])

    def test_a_paid_or_cancelled_payout_is_locked_on_every_field_its_money_rests_on(self):
        rule = self.m["save_rules"][0]
        self.assertEqual((rule["kind"], rule["mode"], rule["states"]),
                         ("locked_in_state", "refuse", [f"{P} Paid", f"{P} Cancelled"]))
        self.assertEqual(set(rule["locked_fields"]),
                         {"consignor", "company", "up_to", "lines", "sales_total", "payout_total", "summary",
                          "worked_out_by", "paid_with", "paid_on", "payment_reference", "paid_by", "lines_paid"})

    def test_the_buttons_are_on_a_draft_payout_and_send_only_its_name(self):
        work, pay = self.m["desk_actions"]
        self.assertEqual((work["label"], work["service"], work["roles"]),
                         ("Work out the payout", "work", ["Accounts User", "Accounts Manager"]))
        self.assertEqual((pay["label"], pay["service"], pay["roles"]), ("Pay this payout", "pay", ["Accounts Manager"]))
        for a in (work, pay):
            self.assertEqual((a["record_type"], a["placement"], a["send_fields"], a["conditions"]),
                             (f"{P} Payout", "form", "name",
                              [{"field": "workflow_state", "operator": "=", "value": f"{P} Draft"}]))
            self.assertLessEqual(len(a["confirm_text"]), 140)

    def test_nobody_but_a_system_manager_deletes_a_payout(self):
        perms = {p["role"]: p for p in self.types[f"{P} Payout"]["permissions"]}
        self.assertEqual(sorted(r for r, p in perms.items() if p["delete"]), ["System Manager"])
        self.assertEqual(sorted(k for k, v in perms[INT].items() if v == 1), ["read", "write"])
        self.assertEqual(sorted(k for k, v in {p["role"]: p for p in self.types[f"{P} Consignor"]["permissions"]}[INT]
                                .items() if v == 1), ["read"])

    def test_a_payouts_consignor_and_company_are_set_once_and_pay_counts_its_lines(self):
        self.assertEqual((self.pay["consignor"].get("set_only_once"), self.pay["company"].get("set_only_once")), (1, 1))
        self.assertEqual((self.pay["lines_paid"]["fieldtype"], self.pay["lines_paid"].get("read_only")), ("Int", 1))
        self.assertIn("lines_paid", self.m["save_rules"][0]["locked_fields"])

    def test_the_item_fields_name_the_consignor_and_its_own_share(self):
        f = {c["fieldname"]: c for c in self.m["custom_fields"]}
        self.assertEqual((f["pp_csg_consignor"]["dt"], f["pp_csg_consignor"]["options"]), ("Item", f"{P} Consignor"))
        self.assertEqual((f["pp_csg_share"]["dt"], f["pp_csg_share"]["fieldtype"]), ("Item", "Percent"))

    def test_the_addresses_are_the_services(self):
        self.assertEqual(self.m["allowed_urls"], [s["endpoint_url"] for s in self.m["extension_subscriptions"]])
        self.assertEqual({s["key"]: s["point"] for s in self.m["extension_subscriptions"]},
                         {"work": "desk_action", "pay": "desk_action"})


if __name__ == "__main__":
    unittest.main()
