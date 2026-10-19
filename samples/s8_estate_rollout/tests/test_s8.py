"""Laptop tests of S8, no bench: the roll-out's plan / apply / verify / remove against an in-memory shop.

    python3 -m unittest discover -s samples/s8_estate_rollout/tests -p 'test_*.py'
"""

import copy
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import generate_estate  # noqa: E402
import rollout as R  # noqa: E402


def _like(v, pat):
    return v is not None and str(v).startswith(pat.rstrip("%"))


class FakeShop(R.Shop):
    """The few record-API behaviours the roll-out uses, in memory (names, like-filters, child tables as lists)."""

    def __init__(self, est):
        self.db, self.writes, self.sold = {}, [], set()
        for dt, names in (("Print Format", {f for s in est["stores"] for f in [s["print_format"]]}), ("Item", est["items"]),
                          ("Role", {r for v in est["roles"].values() for r in v})):
            for n in names:
                self.db[(dt, n)] = {"name": n}
        self.db[("POS Profile", est["reference_profile"])] = {"name": est["reference_profile"], "company": est["company"], "currency": "USD",
                                                              "payments": [{"mode_of_payment": "Cash", "name": "x"}], "warehouse": "ref"}
        self.db[("Retail Setting", "Retail Setting")] = {"name": "Retail Setting", "reason_sale_discount": 0}

    def get(self, dt, name):
        r = self.db.get((dt, name))
        return copy.deepcopy(r) if r else None

    def list(self, dt, filters, fields):
        out = []
        for (d, n), r in self.db.items():
            if d != dt:
                continue
            ok = True
            for f, op, v in filters:
                val = n if f == "name" else r.get(f)
                ok &= _like(val, v) if op == "like" else val == v
            if ok:
                out.append({k: r.get(k) for k in fields} | {"name": r.get("name", n)})
        return out

    def create(self, dt, doc, name=None):
        self.writes.append(("create", dt))
        n = name or doc.get("price_list_name") or doc.get("id") or doc.get("email") or doc.get("warehouse_name")
        r = copy.deepcopy(doc)
        if dt == "Warehouse":
            n = f"{doc['warehouse_name']} - DR"
        if dt == "Item Price":
            n = f"IP-{len(self.db)}"
            r["item_code"] = doc["item_code"]
        if dt == "User Permission":
            n = f"UP-{len(self.db)}"
        r["name"] = n
        r.setdefault("disabled", 0) if dt in ("Warehouse", "POS Profile") else None     # the shop's own defaults
        r.setdefault("enabled", 1) if dt in ("User", "Price List") else None
        r.setdefault("active", 1) if dt == "Promotion Bonus Buys Master" else None
        self.db[(dt, n)] = r
        return r

    def update(self, dt, name, fields):
        self.writes.append(("update", dt))
        r = self.db[(dt, name)]
        for k, v in fields.items():
            if k == "table_applicable_source":
                r[k] = v
            else:
                r[k] = v
        return r

    def delete(self, dt, name):
        self.writes.append(("delete", dt))
        if name in self.sold:
            return False
        del self.db[(dt, name)]
        return True


def _norm_db(shop):
    """Make the fake's stored docs readable the way the Reader reads them from the real shop."""
    for (dt, n), r in list(shop.db.items()):
        if dt == "Item Price":
            r.setdefault("price_list", r.get("price_list"))
        if dt == "Promotion Bonus Buys Master" and "table_applicable_source" in r:
            r["table_applicable_source"] = r["table_applicable_source"]


class Rollout(unittest.TestCase):
    def tearDown(self):
        if os.path.exists(R.BEFORE):
            os.remove(R.BEFORE)

    def setUp(self):
        self.est = generate_estate.build(51)
        self.shop = FakeShop(self.est)
        self.shop.get = self._get   # promotions and users carry child lists the Reader reads
        R.BEFORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".test_before.json")

    def _get(self, dt, name):
        r = FakeShop.get(self.shop, dt, name)
        if r and dt == "User":
            r.setdefault("enabled", 1)
            r["roles"] = r.get("roles", [])
        if r and dt == "Promotion Bonus Buys Master":
            r["table_applicable_source"] = r.get("table_applicable_source", [])
        return r

    def run_steps(self, est=None):
        est = est or self.est
        steps, unchanged, blockers, orphans = R.compute(self.shop, est)
        R.apply_steps(self.shop, est, steps)
        return steps

    def test_plan_on_an_empty_estate_lists_everything_and_writes_nothing(self):
        before = len(self.shop.db)
        steps, unchanged, blockers, orphans = R.compute(self.shop, self.est)
        self.assertEqual(len(self.shop.db), before)
        self.assertEqual(self.shop.writes, [])
        self.assertEqual(blockers, [])
        kinds = {}
        for s in steps:
            kinds[s["dt"]] = kinds.get(s["dt"], 0) + 1
        self.assertEqual((kinds["Warehouse"], kinds["POS Profile"], kinds["Price List"], kinds["Promotion Bonus Buys Master"]), (51, 51, 3, 3))
        self.assertEqual(kinds["User"], 54)
        self.assertEqual(kinds["Item Price"], 9)

    def test_apply_twice_the_second_changes_nothing(self):
        first = self.run_steps()
        self.assertGreater(len(first), 150)
        self.shop.writes.clear()
        second = self.run_steps()
        self.assertEqual(second, [])
        self.assertEqual(self.shop.writes, [])

    def test_a_blocker_is_named(self):
        est = copy.deepcopy(self.est)
        est["stores"][0]["print_format"] = "No Such Format"
        _s, _u, blockers, _o = R.compute(self.shop, est)
        self.assertTrue(any("No Such Format" in b for b in blockers))

    def test_one_price_changes_only_that_row(self):
        self.run_steps()
        est = copy.deepcopy(self.est)
        est["regions"][1]["prices"]["CASE-PHONE"] = 33.0
        steps, _u, _b, _o = R.compute(self.shop, est)
        self.assertEqual([(s["op"], s["dt"], s["name"]) for s in steps], [("update", "Item Price", "PP EST South / CASE-PHONE")])
        self.assertEqual(steps[0]["diff"]["price_list_rate"], [28.13, 33.0])
        R.apply_steps(self.shop, est, steps)                  # the write reaches the record by ITS id, not the row's label
        self.assertEqual([r["price_list_rate"] for r in self.shop.db.values() if r.get("price_list") == "PP EST South" and r.get("item_code") == "CASE-PHONE"], [33.0])
        self.assertEqual(R.compute(self.shop, est)[0], [])

    def test_a_hand_edited_store_is_named_and_apply_repairs_only_it(self):
        self.run_steps()
        self.shop.db[("POS Profile", "PP EST N005")]["print_format"] = "Gift Receipt"
        steps, _u, _b, _o = R.compute(self.shop, self.est)
        self.assertEqual([(s["dt"], s["name"], list(s["diff"])) for s in steps], [("POS Profile", "PP EST N005", ["print_format"])])
        R.apply_steps(self.shop, self.est, steps)
        self.assertEqual(R.compute(self.shop, self.est)[0], [])

    def test_an_orphan_is_named(self):
        self.run_steps()
        self.shop.db[("Warehouse", "PP EST ZZZ - DR")] = {"name": "PP EST ZZZ - DR", "company": self.est["company"], "disabled": 0}
        _s, _u, _b, orphans = R.compute(self.shop, self.est)
        self.assertEqual(orphans, [{"dt": "Warehouse", "name": "PP EST ZZZ - DR"}])

    def test_a_hand_changed_role_and_a_stray_user_permission_are_found_and_repaired(self):
        self.run_steps()
        u = "pp-est-n003@demo-retail.example"
        self.shop.db[("User", u)]["roles"] = [{"role": "Retail Manager"}]                     # the cashier was made a manager by hand
        self.shop.db[("User Permission", "UP-stray")] = {"name": "UP-stray", "user": u, "allow": "POS Profile", "for_value": "PP EST S001"}
        steps, _u, _b, _o = R.compute(self.shop, self.est)
        self.assertEqual(sorted((s["op"], s["dt"], s["name"]) for s in steps),
                         [("delete", "User Permission", f"{u} | POS Profile | PP EST S001"), ("update", "User", u)])
        R.apply_steps(self.shop, self.est, steps)
        self.assertNotIn(("User Permission", "UP-stray"), self.shop.db)                       # the file is the whole truth for an estate user's permissions
        self.assertEqual(R.compute(self.shop, self.est)[0], [])

    def test_an_item_price_dropped_from_the_file_or_added_by_hand_is_an_orphan(self):
        self.run_steps()
        est = copy.deepcopy(self.est)
        del est["regions"][2]["prices"]["EARBUDS"]                       # dropped from the file, still live in the shop
        _s, _u, _b, orphans = R.compute(self.shop, est)
        self.assertEqual(orphans, [{"dt": "Item Price", "name": "PP EST West / EARBUDS"}])
        self.shop.db[("Item Price", "IP-hand")] = {"name": "IP-hand", "item_code": "CABLE-USBC-1M", "price_list": "PP EST North", "price_list_rate": 1.0}
        _s, _u, _b, orphans = R.compute(self.shop, self.est)               # a second row for the same item and list, made by hand
        self.assertEqual(orphans, [{"dt": "Item Price", "name": "PP EST North / CABLE-USBC-1M (row IP-hand)"}])

    def test_a_promotion_reaches_only_its_regions_stores(self):
        self.run_steps()
        promo = self.shop.db[("Promotion Bonus Buys Master", "PP-EST-N")]
        stores = {s["code"] for s in self.est["stores"] if s["region"] == "N"}
        self.assertEqual({w["source"] for w in promo["table_applicable_source"]}, {f"PP EST {c} - DR" for c in stores})

    def test_remove_retires_what_a_sale_points_at_and_deletes_the_rest(self):
        self.run_steps()
        self.shop.sold.add("PP EST N001")
        out = R.remove_all(self.shop, self.est)
        self.assertEqual(out["retired"], ["POS Profile: PP EST N001"])
        self.assertEqual(self.shop.db[("POS Profile", "PP EST N001")]["disabled"], 1)
        self.assertEqual([k for k in self.shop.db if k[0] == "Warehouse"], [])
        self.assertNotIn(("POS Profile", "PP EST N002"), self.shop.db)


if __name__ == "__main__":
    unittest.main()
