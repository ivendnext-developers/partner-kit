"""Laptop tests of the money kit's SETTINGS, no shop: a stub ``frappe`` stands in for the console, so what is tested is how the
kit finds its folder, its shop and its record — never what it rings (that needs a real staging shop).

    python3 -m unittest discover -s tools/moneykit/tests -p 'test_*.py'
"""
import json
import pathlib
import sys
import tempfile
import types
import unittest

KIT = pathlib.Path(__file__).resolve().parents[1]
SHOP = {"cashier": "c@shop.example", "device": "dev-1", "profile": "My Profile", "terminal": "T-1"}


def stub_frappe():
    f = types.ModuleType("frappe")
    f.get_all = lambda *a, **k: []                      # no POS days on the stub shop
    f.set_user = lambda *a, **k: None
    f.db = types.SimpleNamespace(rollback=lambda: None)
    u = types.ModuleType("frappe.utils")
    u.flt = lambda v, *a: float(v or 0)
    u.fmt_money = lambda v, **k: f"{v:.2f}"
    f.utils = u
    sys.modules.update({"frappe": f, "frappe.utils": u})


class T(unittest.TestCase):
    def setUp(self):
        stub_frappe()
        for m in ("till", "baskets"):
            sys.modules.pop(m, None)
        while str(KIT) in sys.path:
            sys.path.remove(str(KIT))
        self.tmp = pathlib.Path(tempfile.mkdtemp())

    def console(self, *steps, with_file=False):
        """Run kit.py the way a console that execs the script's TEXT does (no __file__), or as a file."""
        ns = {"__name__": "pp_console"}
        if with_file:
            ns["__file__"] = str(KIT / "kit.py")
        exec(compile((KIT / "kit.py").read_text(), "kit.py", "exec"), ns, ns)
        out = self.tmp / "out.json"
        ns["main"]([f"record:{out}", *steps])
        return json.loads(out.read_text()), ns

    def shop_file(self, **over):
        p = self.tmp / "my shop.json"
        p.write_text(json.dumps({**SHOP, **over}))
        return p

    def test_the_kit_carries_no_shop_of_its_own(self):
        self.assertFalse((KIT / "shop.json").exists(), "a shop.json in the kit would ring at someone's shop by default")
        rec, _ = self.console(f"kit_dir:{KIT}", "pos_day_check")
        self.assertFalse(rec["ok"])
        self.assertIn("no shop cashier is set", rec["error"])

    def test_settings_steps_point_the_kit_at_its_folder_and_the_shop(self):
        rec, ns = self.console(f"kit_dir:{KIT}", f"shop:{self.shop_file()}", "pos_day_check")
        self.assertTrue(rec["ok"], rec.get("error"))
        self.assertEqual(rec["open_days"], [])
        self.assertEqual(rec["settings"]["kit_dir"], str(KIT))
        self.assertEqual(rec["settings"]["shop_values"], SHOP)
        self.assertEqual(rec["settings"]["shop_from"], str(self.shop_file()))
        self.assertEqual(ns["till"].PROFILE, "My Profile")

    def test_without_a_folder_the_text_console_is_told_what_to_give(self):
        rec, _ = self.console(f"shop:{self.shop_file()}", "pos_day_check")
        self.assertFalse(rec["ok"])
        self.assertIn("give the step kit_dir:<folder>", rec["error"])
        rec, _ = self.console(f"shop:{self.shop_file()}", "pos_day_check", with_file=True)
        self.assertTrue(rec["ok"], "run as a file, the kit finds its own folder")

    def test_a_shop_file_missing_a_value_is_refused_before_any_day_opens(self):
        rec, _ = self.console(f"kit_dir:{KIT}", f"shop:{self.shop_file(device='')}", "pos_day_check")
        self.assertFalse(rec["ok"])
        self.assertIn("['device']", rec["error"])

    def test_no_seeder_means_no_seed_and_no_offer(self):
        rec, _ = self.console(f"kit_dir:{KIT}", f"shop:{self.shop_file()}", "seed")
        self.assertFalse(rec["ok"])
        self.assertIn("no promotions seeder was given", rec["error"])

    def test_a_basket_without_an_offer_never_needs_the_seeder(self):
        """The release gate rings with no seeder: a plain basket must reach the till, not stop at the seeder (found by our
        bench run of S12, row KITMONEY). Here the till's preview is absent, so the basket ends 'refused at preview'."""
        rec, ns = self.console(f"kit_dir:{KIT}", f"shop:{self.shop_file()}", "pos_day_check")
        self.assertTrue(rec["ok"], rec.get("error"))
        row = ns["_ring"]({"id": "G001", "source": "gate", "name": "plain", "promo": None, "lines": [["A", 1, None]]})
        self.assertEqual(row["state"], "refused at preview", row)
        self.assertNotIn("seeder", row.get("detail", ""))

    def test_a_shop_given_after_the_kit_has_loaded_is_refused_never_ignored(self):
        rec, _ = self.console(f"kit_dir:{KIT}", f"shop:{self.shop_file()}", "pos_day_check", f"shop:{self.shop_file(profile='Other')}")
        self.assertFalse(rec["ok"])
        self.assertIn("comes before the first other step", rec["error"])

    def test_the_example_shop_has_every_key(self):
        d = json.loads((KIT / "shop.example.json").read_text())
        self.assertTrue(all(d.get(k) for k in SHOP))


if __name__ == "__main__":
    unittest.main()
