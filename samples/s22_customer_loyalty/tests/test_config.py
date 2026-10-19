"""S22's configuration script and manifest: the manifest passes the kit's checker; the receipt's submit right is left
only to the manager and the service; the integration user holds one role; each tier's promotion excludes every other
group; the receipt workflow lists *Overridden* before *Verified*; and remove puts every permission table back."""

import importlib
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path[:0] = [HERE, SAMPLE, os.path.join(KIT, "tools", "manifest")]
import validate  # noqa: E402
from fake_shop import FakeShop  # noqa: E402

with open(os.path.join(SAMPLE, "manifest.json")) as _fh:
    MANIFEST = json.load(_fh)


class Manifest(unittest.TestCase):
    def test_the_manifest_passes_the_kits_checker_with_no_warning(self):
        self.assertEqual(validate.validate(MANIFEST), [])
        self.assertEqual(validate.warnings(MANIFEST), [])

    def test_the_feed_and_the_key_install_switched_off(self):
        (ra,) = MANIFEST["registered_applications"]
        (key,) = MANIFEST["remote_keys"]
        self.assertFalse({"user", "application_user", "enabled"} & set(ra))
        self.assertFalse({"enabled", "consent_given", "secret"} & set(key))


class Config(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.update(PP_BASE="http://shop", PP_KEY="k", PP_SECRET="s", PP_BEFORE=os.path.join(self.tmp, "b.json"))
        self.cfg = importlib.reload(importlib.import_module("apply_config"))
        self.shop = FakeShop()
        self.shop.put("Customer Group", "Individual", is_group=0)
        self.shop.put("Warehouse", "Demo Retail — Store 1", company="Demo Retail", is_group=0)
        self.cfg.T, self.cfg.S, self.cfg.say = self.shop, self.cfg.State(), (lambda *a: None)
        self.before = self.shop.effective("Purchase Receipt")

    def run_all(self):
        self.cfg.prepare()
        self.cfg.apply()

    def test_only_the_manager_and_the_service_may_submit_a_receipt(self):
        self.run_all()
        self.assertEqual(sorted(r["role"] for r in self.shop.effective("Purchase Receipt") if r["submit"]),
                         ["PP LYL Integration", "Stock Manager"])

    def test_the_service_may_make_and_submit_a_receipts_batch_bundle(self):
        # walked on a sandbox: Verify on a batch-tracked receipt makes and submits its Serial and Batch Bundle as the
        # integration user, and failed while the role could only read it
        self.cfg.prepare()
        (r,) = [r for r in self.shop.effective("Serial and Batch Bundle") if r["role"] == "PP LYL Integration"]
        self.assertEqual({k for k in ("read", "create", "write", "submit") if r[k]}, {"read", "create", "write", "submit"})

    def test_the_settings_name_member_cash_only_once_its_payment_method_exists(self):
        self.run_all()
        st = self.shop.db["PP LYL Settings"]["Default"]
        self.assertEqual((st.get("wallet_mode_of_payment"), st["max_redemption_percent"]), (None, 50))
        self.shop.put("Mode of Payment", "Member cash", type="Wallet")          # made when the wallet goes live
        self.cfg.apply()
        self.assertEqual(self.shop.db["PP LYL Settings"]["Default"]["wallet_mode_of_payment"], "Member cash")

    def test_the_integration_user_holds_one_role(self):
        self.shop.put("User", "pp-lyl-service@demo-retail.example", roles=[{"role": "PP LYL Integration"}, {"role": "Workspace Manager"}])
        self.cfg.prepare()
        self.assertEqual(self.shop.db["User"]["pp-lyl-service@demo-retail.example"]["roles"], [{"role": "PP LYL Integration"}])

    def test_each_tier_excludes_every_other_group_and_overridden_comes_first(self):
        self.run_all()
        promos = self.shop.db["Promotion Bonus Buys Master"]
        self.assertEqual(sorted(promos), ["PP LYL Gold 5%", "PP LYL Silver 3%"])
        gold = {r["source"] for r in promos["PP LYL Gold 5%"]["table_promotion_exclusion_list"]}
        self.assertEqual(gold, {"Individual", "PP LYL Bronze", "PP LYL Silver"})
        wf = self.shop.db["Workflow"]["PP LYL Receipt Verification"]
        self.assertEqual([s["state"] for s in wf["states"] if s["doc_status"] == "1"][0], "PP LYL Overridden")

    def test_switch_on_names_the_user_and_ticks_every_followed_record_type(self):
        # the installer leaves the registration with no user and every record type unticked; the shop writes a feed
        # row only for a ticked one, so a user alone would read an empty feed
        events = [{"name": f"e{i}", "doc_type": d, "enable": 0} for i, d in enumerate(("Customer", "POS Invoice"))]
        (ra,) = MANIFEST["registered_applications"]
        self.shop.put("Registered Application", ra["name"], application_user=None, registered_application_events=events)
        self.cfg.switches(1)
        reg = self.shop.db["Registered Application"][ra["name"]]
        self.assertEqual(reg["application_user"], "pp-lyl-service@demo-retail.example")
        self.assertEqual([(e["doc_type"], e["enable"]) for e in reg["registered_application_events"]],
                         [("Customer", 1), ("POS Invoice", 1)])
        self.cfg.switches(0)
        reg = self.shop.db["Registered Application"][ra["name"]]
        self.assertEqual((reg["application_user"], {e["enable"] for e in reg["registered_application_events"]}), (None, {0}))

    def test_only_the_makers_send_allows_self_approval(self):
        self.run_all()
        steps = {t["action"]: t["allow_self_approval"] for t in self.shop.db["Workflow"]["PP LYL Receipt Verification"]["transitions"]}
        self.assertEqual(steps, {"PP LYL Send for Verification": 1, "PP LYL Verify": 0, "PP LYL Override": 0, "PP LYL Cancel": 0})

    def test_remove_puts_the_permissions_back_and_removes_what_it_made(self):
        self.run_all()
        self.run_all()
        self.cfg.remove()
        self.assertEqual(self.shop.effective("Purchase Receipt"), self.before)
        self.assertEqual(self.shop.db.get("Workflow"), {})
        self.assertNotIn("PP LYL Gold", self.shop.db["Customer Group"])

    def test_remove_switches_off_the_user_and_role_a_completed_workflow_step_still_names(self):
        self.run_all()
        self.shop.linked = {"pp-lyl-service@demo-retail.example", "PP LYL Integration"}
        self.cfg.remove()
        self.assertEqual(self.shop.db["User"]["pp-lyl-service@demo-retail.example"]["enabled"], 0)
        self.assertEqual(self.shop.db["Role"]["PP LYL Integration"]["disabled"], 1)
        self.cfg.S = self.cfg.State()
        self.cfg.prepare()                                  # a later prepare switches both back on
        self.assertEqual((self.shop.db["User"]["pp-lyl-service@demo-retail.example"]["enabled"],
                          self.shop.db["Role"]["PP LYL Integration"]["disabled"]), (1, 0))


if __name__ == "__main__":
    unittest.main()
