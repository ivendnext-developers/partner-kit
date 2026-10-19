"""S31's laptop tests: the plan for one record, and the service against an in-memory shop. No shop, no network.

    python3 -m unittest discover -s samples/s31_parent_groups/tests -p 'test_*.py'
"""

import copy
import pathlib
import sqlite3
import sys
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
import expander as X  # noqa: E402
import groups as G  # noqa: E402

TREE = {"All Item Groups": None, "Supplements": "All Item Groups", "Protein": "Supplements", "Whey": "Protein",
        "Vitamins": "Supplements", "Phones": "All Item Groups"}


def get_row(group, **kw):
    return {"source_type": "Item Group", "source_key": group, **kw}


def coupon(*rows):
    return {"name": "PP-PGX-COUPON", "modified": "2026-10-16 10:00:00", "table_get_items": [dict(r, name=f"r{i}") for i, r in enumerate(rows)]}


def promotion(buy=(), get=(), excl=()):
    return {"name": "PP-PGX-PROMO", "modified": "2026-10-16 10:00:00",
            "table_buy_items": [{"source_type": "Item Group", "source_key": g} for g in buy],
            "table_get_items": [{"source_type_internal": "Item Group", "source_type": "Item Group", "source_key": g} for g in get],
            "table_promotion_exclusion_list": [{"source_type": "Item Group", "source": g, "name": f"e{i}"} for i, g in enumerate(excl)]}


class Plan(unittest.TestCase):
    def test_a_coupon_parent_row_gets_every_child_with_its_discount(self):
        p = G.plan(G.COUPON, coupon(get_row("Supplements", discount_type="Percent", discount=10, quantity=1)), TREE, {}, set())
        added = p["add"]["table_get_items"]
        self.assertEqual([r["source_key"] for r in added], ["Protein", "Vitamins", "Whey"])
        self.assertTrue(all(r["discount"] == 10 and r["discount_type"] == "Percent" for r in added))
        self.assertEqual(p["mine"][("table_get_items", "Whey")], "Supplements")

    def test_a_persons_own_child_row_is_not_added_again_nor_claimed(self):
        p = G.plan(G.COUPON, coupon(get_row("Supplements"), get_row("Protein", discount=5)), TREE, {}, set())
        self.assertEqual([r["source_key"] for r in p["add"]["table_get_items"]], ["Vitamins", "Whey"])
        self.assertNotIn(("table_get_items", "Protein"), p["mine"])

    def test_removing_the_parent_drops_only_the_rows_the_service_added(self):
        mine = {("table_get_items", "Vitamins"): "Supplements", ("table_get_items", "Whey"): "Supplements"}
        doc = coupon(get_row("Protein", discount=5), get_row("Vitamins"), get_row("Whey"))      # the parent row is gone
        p = G.plan(G.COUPON, doc, TREE, mine, set())
        # Whey is still under Protein, which a person still lists: only Vitamins goes
        self.assertEqual(sorted(p["drop"]["table_get_items"]), ["Vitamins"])
        after = G.table_after(doc, "table_get_items", "source_type", "source_key", [], p["drop"]["table_get_items"])
        self.assertEqual([r["source_key"] for r in after], ["Protein", "Whey"])

    def test_a_group_moved_out_from_under_the_parent_is_dropped(self):
        mine = {("table_get_items", "Protein"): "Supplements", ("table_get_items", "Vitamins"): "Supplements",
                ("table_get_items", "Whey"): "Supplements"}
        tree = dict(TREE, Vitamins="Phones")
        doc = coupon(get_row("Supplements"), get_row("Protein"), get_row("Vitamins"), get_row("Whey"))
        p = G.plan(G.COUPON, doc, tree, mine, set())
        self.assertEqual(p["drop"], {"table_get_items": ["Vitamins"]})

    def test_a_removed_child_comes_back_when_its_parent_is_listed_again(self):
        removed = {("table_get_items", "Vitamins")}
        p = G.plan(G.COUPON, coupon(get_row("Phones")), TREE, {}, removed)            # the parent left
        self.assertEqual(p["removed"], set())
        p = G.plan(G.COUPON, coupon(get_row("Supplements")), TREE, {}, p["removed"])   # and is listed again
        self.assertIn("Vitamins", [r["source_key"] for r in p["add"]["table_get_items"]])

    def test_a_row_a_person_removed_is_not_added_back(self):
        mine = {("table_get_items", "Protein"): "Supplements", ("table_get_items", "Vitamins"): "Supplements",
                ("table_get_items", "Whey"): "Supplements"}
        p = G.plan(G.COUPON, coupon(get_row("Supplements"), get_row("Protein"), get_row("Whey")), TREE, mine, set())
        self.assertEqual(p["add"], {})
        self.assertIn(("table_get_items", "Vitamins"), p["removed"])

    def test_a_promotion_exclusion_parent_is_written_out(self):
        p = G.plan(G.PROMOTION, promotion(excl=["Supplements"]), TREE, {}, set())
        self.assertEqual([r["source"] for r in p["add"]["table_promotion_exclusion_list"]], ["Protein", "Vitamins", "Whey"])

    def test_a_promotion_buy_or_get_parent_is_flagged_never_written_out(self):
        p = G.plan(G.PROMOTION, promotion(buy=["Supplements"], get=["Protein"]), TREE, {}, set())
        self.assertEqual(p["add"], {})
        self.assertEqual(len(p["flags"]), 2)

    def test_a_leaf_group_needs_nothing(self):
        p = G.plan(G.COUPON, coupon(get_row("Phones")), TREE, {}, set())
        self.assertEqual((p["add"], p["drop"], p["flags"]), ({}, {}, []))


class FakeShop:
    def __init__(self, tree, records):
        self.tree, self.records, self.puts = dict(tree), copy.deepcopy(records), []

    def groups(self):
        return dict(self.tree)

    def names(self, dt):
        return [n for (t, n) in self.records if t == dt]

    def get(self, dt, name):
        return copy.deepcopy(self.records[(dt, name)])

    def put(self, dt, name, body):
        doc = self.records[(dt, name)]
        assert body.pop("modified") == doc["modified"], "the write did not carry the modified it read"
        self.puts.append((dt, name, copy.deepcopy(body)))
        doc.update(body)
        doc["modified"] = doc["modified"] + "+"
        return doc


def db():
    d = sqlite3.connect(":memory:", isolation_level=None)
    X.init(d)
    return d


class Service(unittest.TestCase):
    def setUp(self):
        self.shop = FakeShop(TREE, {(G.COUPON, "PP-PGX-COUPON"): coupon(get_row("Supplements", discount=10)),
                                    (G.PROMOTION, "PP-PGX-PROMO"): promotion(buy=["Supplements"], excl=["Protein"])})
        self.db = db()
        self.quiet = lambda *_: None

    def test_one_pass_then_a_second_writes_nothing(self):
        n = X.everything(self.shop, self.db, self.quiet)
        self.assertEqual((n["added"], n["flags"]), (4, 1))
        writes = len(self.shop.puts)
        again = X.everything(self.shop, self.db, self.quiet)
        self.assertEqual((again["added"], again["dropped"]), (0, 0))
        self.assertEqual(len(self.shop.puts), writes)

    def test_a_group_added_under_a_listed_parent_joins_on_its_event(self):
        X.everything(self.shop, self.db, self.quiet)
        self.shop.tree["Omega"] = "Supplements"
        X.handler(self.shop, self.quiet)({"doc_type": "Item Group", "doc_name": "Omega", "event": "created"}, self.db)
        keys = [r["source_key"] for r in self.shop.records[(G.COUPON, "PP-PGX-COUPON")]["table_get_items"]]
        self.assertIn("Omega", keys)

    def test_a_refused_record_rolls_back_only_itself(self):
        real = self.shop.put

        def refuse_promotion(dt, name, body):
            if dt == G.PROMOTION:
                raise X.F.FeedError("417 Document has been modified after you have opened it")
            return real(dt, name, body)
        self.shop.put = refuse_promotion
        self.db.execute("begin")
        n = X.everything(self.shop, self.db, self.quiet)
        self.db.execute("commit")
        self.assertEqual((n["failed"], n["records"]), (1, 1))
        kept = {r[0] for r in self.db.execute("select record from ours")}
        self.assertEqual(kept, {"PP-PGX-COUPON"}, "the coupon's own rows were lost with the promotion's refusal")

    def test_a_persons_row_survives_the_parent_being_removed(self):
        c = self.shop.records[(G.COUPON, "PP-PGX-COUPON")]
        c["table_get_items"].append(get_row("Vitamins", discount=3, name="person"))
        X.everything(self.shop, self.db, self.quiet)
        c["table_get_items"] = [r for r in c["table_get_items"] if r["source_key"] != "Supplements"]
        X.one(self.shop, self.db, G.COUPON, "PP-PGX-COUPON", out=self.quiet)
        self.assertEqual([r["source_key"] for r in c["table_get_items"]], ["Vitamins"])
        self.assertEqual(c["table_get_items"][0]["discount"], 3)


if __name__ == "__main__":
    unittest.main()
