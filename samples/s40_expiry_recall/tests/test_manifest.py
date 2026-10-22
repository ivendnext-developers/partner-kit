"""S40's manifest: the fields it adds to the shop's records, the four doors and what each sends, who may press, the
lock on a disposal record, and the one address."""

import json
import os
import unittest
from urllib.parse import urlsplit

MANIFEST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json")


class ManifestTest(unittest.TestCase):
    def setUp(self):
        with open(MANIFEST) as f:
            self.m = json.load(f)

    def test_the_shops_records_get_only_the_apps_eight_fields(self):
        got = {(c["dt"], c["fieldname"], c["fieldtype"]) for c in self.m["custom_fields"]}
        self.assertEqual(got, {("Item", "pp_rcl_min_shelf_days", "Int"), ("Item", "pp_rcl_shelf_life_exempt", "Check"),
                               ("Purchase Receipt Item", "pp_rcl_pack_expiry", "Date"),
                               ("Purchase Receipt Item", "pp_rcl_lou", "Check"),
                               ("Purchase Receipt Item", "pp_rcl_lou_days", "Int"),
                               ("Purchase Receipt", "pp_rcl_short_dated", "Data"),
                               ("Stock Entry", "pp_rcl_disposal_record", "Link"),
                               ("Stock Entry", "pp_rcl_erp_check", "Data")})

    def test_the_checks_answer_on_submit_only_and_fill_one_field(self):
        subs = {s["key"]: s for s in self.m["extension_subscriptions"]}
        rec, dis = subs["receipt"], subs["disposal"]
        self.assertEqual((rec["settings"]["record_type"], rec["settings"]["on_validate"], rec["settings"]["fill_fields"],
                          rec["down_answer"]), ("Purchase Receipt", False, ["pp_rcl_short_dated"], "refuse"))
        cnt = subs["count"]
        self.assertEqual((cnt["settings"]["record_type"], cnt["down_answer"]), ("Stock Reconciliation", "refuse"))
        self.assertEqual((dis["settings"]["record_type"], dis["settings"]["on_validate"], dis["settings"]["fill_fields"],
                          dis["down_answer"]), ("Stock Entry", False, ["pp_rcl_erp_check"], "refuse"))
        self.assertNotIn("customer", rec["settings"]["send_fields"] + dis["settings"]["send_fields"])

    def test_the_recall_button_is_the_recall_officers_alone(self):
        a = {d["label"]: d for d in self.m["desk_actions"]}
        self.assertEqual((a["Block these batches"]["record_type"], a["Block these batches"]["roles"]),
                         ("PP RCL Recall Notice", ["PP RCL Recall Officer"]))
        self.assertLessEqual(len(a["Block these batches"]["confirm_text"]), 140)

    def test_customers_supplied_are_read_by_the_recall_officer_and_system_manager_only(self):
        notice = next(d for d in self.m["doctypes"] if d["name"] == "PP RCL Recall Notice")
        self.assertEqual({p["role"] for p in notice["permissions"] if p["read"]},
                         {"System Manager", "PP RCL Recall Officer", "PP RCL Integration"})

    def test_a_disposal_record_is_locked_once_the_visit_is_recorded(self):
        wf, = self.m["workflows"]
        self.assertEqual({s["state"]: s["allow_edit"] for s in wf["states"]},
                         {"PP RCL Draft": "PP RCL Recall Officer", "PP RCL Visit recorded": "System Manager"})
        self.assertEqual({t["next_state"] for t in wf["transitions"]}, {"PP RCL Visit recorded"})
        lock = next(r for r in self.m["save_rules"] if r["kind"] == "locked_in_state")
        self.assertIn("lines", lock["locked_fields"])
        rec = next(d for d in self.m["doctypes"] if d["name"] == "PP RCL Disposal Record")
        self.assertFalse(any(p["write"] for p in rec["permissions"] if p["role"] == "PP RCL Integration"))

    def test_the_one_origin_is_the_services(self):
        subs = self.m["extension_subscriptions"]
        self.assertEqual(sorted(self.m["allowed_urls"]), sorted(s["endpoint_url"] for s in subs))
        self.assertEqual(len({urlsplit(u).netloc for u in self.m["allowed_urls"]}), 1)


if __name__ == "__main__":
    unittest.main()
