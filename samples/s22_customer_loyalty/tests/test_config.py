"""S22's configuration script and manifest: the manifest passes the kit's checker and holds the tiers, the default
settings and the app role's rights beyond the feed's reads; the receipt's submit right is left only to the manager and
the service; the install's user is left alone; each tier's promotion excludes every other group; the receipt workflow
lists *Overridden* before *Verified*; and remove puts every permission table back."""

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

    def test_the_tiers_the_settings_and_the_roles_rights_are_the_manifests(self):
        by_type = {}
        for r in MANIFEST["records"]:
            by_type.setdefault(r["doctype"], []).append(r["name"])
        self.assertEqual(by_type, {"Customer Group": ["PP LYL Bronze", "PP LYL Silver", "PP LYL Gold"],
                                   "PP LYL Plan": ["Bronze", "Silver", "Gold"], "PP LYL Settings": ["Default"]})
        # a plan's group and the settings' default plan come before their link: the install makes rows in this order
        order = [(r["doctype"], r["name"]) for r in MANIFEST["records"]]
        self.assertLess(order.index(("Customer Group", "PP LYL Gold")), order.index(("PP LYL Plan", "Gold")))
        self.assertLess(order.index(("PP LYL Plan", "Bronze")), order.index(("PP LYL Settings", "Default")))
        rights = {r["doctype"]: (r["role"], tuple(r["rights"])) for r in MANIFEST["role_rights"]}
        # the feed's reads (Customer, POS Invoice, Purchase Receipt) are the install's: only Customer's write and two
        # reads the feed does not follow are the manifest's
        self.assertEqual(rights, {"Customer": ("PP LYL Integration", ("read", "write")),
                                  "Purchase Order": ("PP LYL Integration", ("read",)),
                                  "Supplier": ("PP LYL Integration", ("read",))})
        # what is per retailer stays out of the manifest
        values = [v for r in MANIFEST["records"] if r["doctype"] == "PP LYL Settings" for v in r["values"]]
        self.assertFalse({"currency", "currency_precision", "walk_in_customers", "wallet_mode_of_payment"} & set(values))

    def test_the_feed_and_the_key_install_switched_off(self):
        (ra,) = MANIFEST["registered_applications"]
        (key,) = MANIFEST["remote_keys"]
        self.assertFalse({"user", "application_user", "enabled"} & set(ra))
        self.assertFalse({"enabled", "consent_given", "secret"} & set(key))

    def test_the_english_words_cover_every_name_the_store_sees(self):   # Desk shows people's words, never the code
        with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "manifest.json"), encoding="utf-8") as f:
            m = json.load(f)
        names = {d["name"] for d in m.get("doctypes", [])}
        for key in ("print_formats", "reports", "registered_applications", "sale_attributes", "workspaces",
                    "number_cards", "notifications", "dashboard_charts"):
            names |= {x["name"] for x in m.get(key, [])}
        for wf in m.get("workflows", []):
            names |= {wf["name"]} | {s["state"] for s in wf["states"]} | {t["action"] for t in wf["transitions"]}
        for d in m.get("doctypes", []):
            names |= {p["role"] for p in d.get("permissions", []) if not p["role"].endswith(" Integration")}
        (en,) = [t["words"] for t in m["translations"] if t["language"] == "en"]
        self.assertEqual(sorted(n for n in names if n.startswith(m["prefix"]) and n not in en), [])
        self.assertTrue(all(w and not w.startswith(m["prefix"]) for w in en.values()))


RECEIPT_CHECK = {"keep_submit": ["Stock Manager", "PP LYL Integration"], "integration_rights": [{"doctype": "Purchase Receipt", "rights": ["read", "write", "submit"], "why": "take the Verify step, which submits the receipt"}, {"doctype": "Serial and Batch Bundle", "rights": ["read", "create", "write", "submit"], "why": "the Verify step submits the receipt; for a batch-tracked item that makes and submits its batch bundle as the integration user"}]}


class Config(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.update(PP_BASE="http://shop", PP_KEY="k", PP_SECRET="s", PP_BEFORE=os.path.join(self.tmp, "b.json"))
        self.cfg = importlib.reload(importlib.import_module("apply_config"))
        self.shop = FakeShop()
        self.shop.put("Customer Group", "Individual", is_group=0)
        self.shop.put("Role", "PP LYL Integration", disabled=0)       # the install makes the app's role and its one user
        for r in MANIFEST["records"]:                                  # ... and the manifest's default records
            self.shop.put(r["doctype"], r["name"], **r["values"])
        self.shop.put("Warehouse", "Demo Retail — Store 1", company="Demo Retail", is_group=0)
        self.cfg.T, self.cfg.S, self.cfg.say = self.shop, self.cfg.State(), (lambda *a: None)
        self.before = self.shop.effective("Purchase Receipt")
        self.shipped = self.cfg.CONF
        self.cfg.CONF = dict(self.shipped, receipt_workflow=RECEIPT_CHECK)

    def run_all(self):
        self.cfg.prepare()
        self.cfg.apply()

    def test_as_shipped_nobody_loses_submit_on_a_receipt(self):
        self.cfg.CONF = self.shipped
        self.run_all()
        submits = lambda rows: {r["role"] for r in rows if r["submit"]}     # noqa: E731
        self.assertEqual(submits(self.shop.effective("Purchase Receipt")), submits(self.before))
        self.assertFalse(self.shop.db.get("Workflow"))

    def test_only_the_manager_and_the_service_may_submit_a_receipt(self):
        self.run_all()
        self.assertEqual(sorted(r["role"] for r in self.shop.effective("Purchase Receipt") if r["submit"]),
                         sorted(["PP LYL Integration", "Stock Manager"]))  # the app's own role sorts by its prefix

    def test_the_service_may_make_and_submit_a_receipts_batch_bundle(self):
        # walked on a sandbox: Verify on a batch-tracked receipt makes and submits its Serial and Batch Bundle as the
        # integration user, and failed while the role could only read it
        self.cfg.prepare()
        (r,) = [r for r in self.shop.effective("Serial and Batch Bundle") if r["role"] == "PP LYL Integration"]
        self.assertEqual({k for k in ("read", "create", "write", "submit") if r[k]}, {"read", "create", "write", "submit"})

    def test_the_settings_name_member_cash_only_once_its_payment_method_exists(self):
        self.run_all()
        st = self.shop.db["PP LYL Settings"]["Default"]
        self.assertEqual((st.get("wallet_mode_of_payment"), st["max_redemption_percent"], st["currency"]), (None, 50, "USD"))
        self.shop.put("Mode of Payment", "Member cash", type="Wallet")          # made when the wallet goes live
        self.cfg.apply()
        self.assertEqual(self.shop.db["PP LYL Settings"]["Default"]["wallet_mode_of_payment"], "Member cash")

    def test_prepare_makes_no_user_and_asks_for_the_install_first(self):
        self.cfg.prepare()
        self.assertFalse(self.shop.db.get("User"))                     # the install's user is the app's: never a hand-made one
        del self.shop.db["Role"]["PP LYL Integration"]
        with self.assertRaises(SystemExit) as e:
            self.cfg.prepare()
        self.assertIn("install the app first", str(e.exception))

    def test_prepare_grants_nothing_until_a_receipt_check_is_added(self):
        self.cfg.CONF = self.shipped
        self.cfg.prepare()                                              # the feed's reads and role_rights are the install's
        self.assertEqual([r for r in self.shop.effective("Customer") if r["role"] == "PP LYL Integration"], [])

    def test_each_tier_excludes_every_other_group_and_overridden_comes_first(self):
        self.run_all()
        promos = self.shop.db["Promotion Bonus Buys Master"]
        self.assertEqual(sorted(promos), ["PP LYL Gold 5%", "PP LYL Silver 3%"])
        gold = {r["source"] for r in promos["PP LYL Gold 5%"]["table_promotion_exclusion_list"]}
        self.assertEqual(gold, {"Individual", "PP LYL Bronze", "PP LYL Silver"})
        wf = self.shop.db["Workflow"]["PP LYL Receipt Verification"]
        self.assertEqual([s["state"] for s in wf["states"] if s["doc_status"] == "1"][0], "PP LYL Overridden")

    def test_a_tiers_promotion_follows_the_shops_live_plan_not_the_manifest(self):
        self.shop.db["PP LYL Plan"]["Gold"]["discount_percent"] = 7          # the retailer changed it in Desk
        self.shop.db["PP LYL Plan"]["Silver"]["active"] = 0                  # and switched a tier off
        self.run_all()
        self.assertEqual(sorted(self.shop.db["Promotion Bonus Buys Master"]), ["PP LYL Gold 7%"])

    def test_switch_on_ticks_every_followed_record_type_and_leaves_the_installs_user(self):
        # the installer names the app's user and leaves every record type unticked; the shop writes a feed row only for
        # a ticked one, so a user alone would read an empty feed
        events = [{"name": f"e{i}", "doc_type": d, "enable": 0} for i, d in enumerate(("Customer", "POS Invoice"))]
        (ra,) = MANIFEST["registered_applications"]
        self.shop.put("Registered Application", ra["name"], application_user="pp_lyl@integration.invalid",
                      registered_application_events=events)
        self.cfg.switches(1)
        reg = self.shop.db["Registered Application"][ra["name"]]
        self.assertEqual(reg["application_user"], "pp_lyl@integration.invalid")
        self.assertEqual([(e["doc_type"], e["enable"]) for e in reg["registered_application_events"]],
                         [("Customer", 1), ("POS Invoice", 1)])
        self.cfg.switches(0)
        reg = self.shop.db["Registered Application"][ra["name"]]
        self.assertEqual((reg["application_user"], {e["enable"] for e in reg["registered_application_events"]}),
                         ("pp_lyl@integration.invalid", {0}))

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
        self.assertIn("PP LYL Gold", self.shop.db["Customer Group"])   # the install's default record: this script never made it


if __name__ == "__main__":
    unittest.main()
