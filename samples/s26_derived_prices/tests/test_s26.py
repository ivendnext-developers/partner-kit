"""Laptop tests of S26, no shop: the arithmetic, the rule checks, and the service against an in-memory shop.

    python3 -m unittest discover -s samples/s26_derived_prices/tests -p 'test_*.py'
"""

import datetime as dt
import os
import sqlite3
import sys
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import prices as P  # noqa: E402
import sync as S  # noqa: E402

TODAY = dt.date(2026, 10, 16)


def rule(name="R", src="BUY", tgt="SELL", factor="1.5", offset="0", step="0.01", rounding="Nearest", floor="0", enabled=1,
         places=2):
    return {"name": name, "source_price_list": src, "target_price_list": tgt, "factor": factor, "offset": offset,
            "rounding_step": step, "rounding": rounding, "floor": floor, "enabled": enabled, "decimal_places": places}


class FakeShop:
    """Item prices, price lists and rules in memory. The service writes as "svc"; ``person`` edits as a person."""

    def __init__(self, rules, lists=None):
        self._rules = rules
        self.cur = lists or {"BUY": "USD", "SELL": "USD", "WHOLESALE": "USD", "JPY": "JPY"}
        self.data, self.n, self.writes, self.pages = {}, 0, [], []

    def me(self):
        return "svc"

    def rules(self):
        return list(self._rules)

    def lists(self):
        return dict(self.cur)

    def stamped(self, price_list, stamp):
        return [dict(r) for r in self.data.values() if r["price_list"] == price_list and r.get("note") == stamp]

    def price(self, name):
        return dict(self.data[name]) if name in self.data else None

    def rows(self, price_list, item=None, uom=None, after="", limit=0):
        out = sorted((dict(r) for r in self.data.values() if r["price_list"] == price_list and P.general(r)
                      and (item is None or (r["item_code"], r["uom"]) == (item, uom)) and r["name"] > after),
                     key=lambda r: r["name"])
        if item is None:
            self.pages.append(after)
        return out[:limit] if limit else out

    def made_from(self, source_row):
        return [dict(r) for r in self.data.values() if (r.get("note") or "").startswith("PP-DPL ")
                and r["note"].split(" ")[-1] == source_row]

    def _new(self, doc, by):
        self.n += 1
        name = doc.get("name") or f"ip{self.n:03d}"
        self.data[name] = {"name": name, "valid_from": str(TODAY), "valid_upto": None, "note": None, "customer": None,
                           "supplier": None, "batch_no": None, **doc, "modified_by": by}
        return name

    def insert(self, doc):
        name = self._new(doc, "svc")
        self.writes.append(("insert", name))
        return dict(self.data[name])

    def update(self, name, fields):
        self.writes.append(("update", name))
        self.data[name].update(fields, modified_by="svc")
        return dict(self.data[name])

    # the test's own hands
    def put(self, plist, item, rate, name=None, uom="Nos", **k):
        return self._new({"name": name, "item_code": item, "uom": uom, "price_list": plist, "price_list_rate": rate, **k}, "person")

    def person(self, name, **f):
        self.data[name].update(f, modified_by="person")

    def at(self, plist, item="A"):
        return [r for r in self.data.values() if r["price_list"] == plist and r["item_code"] == item]


class Base(unittest.TestCase):
    rules = [rule()]

    def setUp(self):
        self.shop = FakeShop(self.rules)
        self.db = sqlite3.connect(":memory:", isolation_level=None)
        self.svc = S.Service(self.shop, self.db, today=TODAY)
        self.svc.load()

    def event(self, name, label="item_price.on_update"):
        self.svc.handler({"id": "e", "event": label, "doc_type": "Item Price", "doc_name": name}, None)


# ---------------------------------------------------------------------------------------------- 1. the arithmetic
class Formula(unittest.TestCase):
    def d(self, src, **k):
        return P.derive(src, P.Rule(rule(**k)))

    def test_rounding_table(self):
        cases = [
            (dict(), "6.67", "10.01"),                              # 10.005: half up at 0.01
            (dict(step="0.05"), "6.67", "10.00"),                   # nearest 0.05
            (dict(step="0.05", rounding="Up"), "6.68", "10.05"),    # 10.02 up to 0.05
            (dict(step="0.5", rounding="Down"), "7.16", "10.50"),   # 10.74 down to 0.5
            (dict(step="1"), "7", "11.00"),                         # 10.5: half up at 1
            (dict(factor="0.9", step="1", rounding="Down"), "99", "89.00"),
            (dict(offset="0.99", step="0.01"), "10", "15.99"),     # an offset after the factor
            (dict(factor="1"), "1.005", "1.01"),                    # Decimal: a float would make this 1.00
            (dict(), "66.67", "100.01"),                            # 100.005 (the sandbox run): a float makes it 100.00
        ]
        for k, src, want in cases:
            self.assertEqual(self.d(src, **k), (Decimal(want), False), (k, src))

    def test_the_floor_raises_and_says_so(self):
        self.assertEqual(self.d("2", floor="5"), (Decimal("5.00"), True))
        self.assertEqual(self.d("10", offset="-20"), (Decimal("0.00"), True))
        rate, raised = self.d("10", factor="1", offset="-10.004")                 # -0.004 rounds to -0.00: written 0.00, and said
        self.assertEqual((str(rate), raised), ("0.00", True))     # below 0: raised to a floor of 0, and said

    def test_a_zero_decimal_currency(self):
        self.assertEqual(self.d("1500", places=0, factor="0.9", step="1"), (Decimal("1350"), False))
        self.assertEqual(str(self.d("1501", places=0, factor="0.9", step="1")[0]), "1351")
        self.assertEqual(str(self.d("10", places=3, factor="1.0005")[0]), "10.010")     # the 0.01 step first, then written at 3 places


class RuleChecks(unittest.TestCase):
    cur = {"A": "USD", "B": "USD", "C": "USD", "J": "JPY", "K": "JPY"}

    def use(self, *rs):
        return P.usable(list(rs), self.cur)

    def test_a_loop_is_refused(self):
        ok, refused = self.use(rule("AB", "A", "B"), rule("BC", "B", "C"), rule("CA", "C", "A"))
        self.assertEqual(ok, {})
        self.assertEqual({r["rule"] for r in refused}, {"AB", "BC", "CA"})
        self.assertIn("loop", refused[0]["why"])

    def test_a_chain_without_a_loop_runs(self):
        ok, refused = self.use(rule("AB", "A", "B"), rule("BC", "B", "C"))
        self.assertEqual((sorted(ok), refused), (["AB", "BC"], []))

    def test_two_rules_on_one_target_are_both_refused(self):
        ok, refused = self.use(rule("AC", "A", "C"), rule("BC", "B", "C"))
        self.assertEqual((ok, sorted(r["rule"] for r in refused)), ({}, ["AC", "BC"]))

    def test_each_bad_rule_is_refused_with_its_reason(self):
        for r, words in ((rule("x", "A", "J"), "different currencies"), (rule("x", "J", "J"), "same list"),
                         (rule("x", "A", "B", factor="0"), "factor"), (rule("x", "A", "B", step="0.02"), "rounding step"),
                         (rule("x", "A", "Z"), "not in the shop"), (rule("x", "A", "B", factor="abc"), "not a number"),
                         (rule("x", "A", "B", places=9), "decimal places")):
            ok, refused = self.use(r)
            self.assertEqual(ok, {}, words)
            self.assertIn(words, refused[0]["why"])

    def test_a_step_or_floor_finer_than_the_places_is_refused(self):
        ok, refused = self.use(rule("x", "J", "K", step="0.05", places=0))
        self.assertIn("finer than 0 decimal places", refused[0]["why"])
        self.assertIn("finer than", self.use(rule("x", "J", "K", step="1", floor="4.5", places=0))[1][0]["why"])
        self.assertEqual(sorted(self.use(rule("x", "J", "K", step="1", places=0))[0]), ["x"])

    def test_a_disabled_rule_is_neither_run_nor_refused(self):
        self.assertEqual(self.use(rule("x", "A", "B", enabled=0)), ({}, []))


# ---------------------------------------------------------------------------------------------- 2. one event, one row
class Feed(Base):
    def test_a_source_change_writes_the_target(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        [t] = self.shop.at("SELL")
        self.assertEqual((t["price_list_rate"], t["note"], t["valid_from"]), ("15.00", "PP-DPL R b1", str(TODAY)))
        self.shop.person("b1", price_list_rate=12.0)
        self.event("b1")
        self.assertEqual([r["price_list_rate"] for r in self.shop.at("SELL")], ["18.00"])

    def test_one_event_twice_writes_one_row(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        self.event("b1")
        self.event("b1", "item_price.on_change")
        self.assertEqual(len(self.shop.at("SELL")), 1)
        self.assertEqual(self.shop.writes, [("insert", "ip002")])

    def test_a_row_for_one_customer_is_not_derived(self):
        self.shop.put("BUY", "A", 10.0, name="b1", customer="C1")
        self.event("b1")
        self.assertEqual(self.shop.at("SELL"), [])


class PersonsPrice(Base):
    def test_a_persons_price_at_the_target_is_held_and_reported(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.shop.put("SELL", "A", 13.0, name="s1")
        rep = S.report()
        self.svc.on_row(self.shop.price("b1"), rep)
        self.assertEqual([(r["name"], r["price_list_rate"]) for r in self.shop.at("SELL")], [("s1", 13.0)])
        self.assertEqual((self.shop.writes, rep["held"][0]["why"]), ([], "a price at the target that the service did not make"))

    def test_a_derived_price_a_person_changed_is_held(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        [t] = self.shop.at("SELL")
        self.shop.person(t["name"], price_list_rate=14.0)
        self.shop.person("b1", price_list_rate=20.0)
        rep = S.report()
        self.svc.on_row(self.shop.price("b1"), rep)
        self.assertEqual(self.shop.at("SELL")[0]["price_list_rate"], 14.0)
        self.assertEqual(rep["held"][0]["why"], "changed by a person since the service wrote it")


class Folds(Base):
    """What the review found: an ended person's price, another rule's row, a re-enabled rule, a source row edited."""

    def test_an_ended_persons_price_does_not_block(self):
        self.shop.put("SELL", "A", 13.0, name="s1", valid_upto="2026-10-01")
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        self.assertEqual({r["name"]: r["price_list_rate"] for r in self.shop.at("SELL")}, {"s1": 13.0, "ip003": "15.00"})

    def test_a_row_left_by_another_rule_is_held_with_that_reason(self):
        self.shop.put("SELL", "A", 13.0, name="s1", note="PP-DPL OLD b0")
        self.shop.put("BUY", "A", 10.0, name="b1")
        rep = S.report()
        self.svc.on_row(self.shop.price("b1"), rep)
        self.assertEqual((self.shop.writes, rep["held"][0]["why"]), ([], "made by another rule, or by a rule since deleted"))

    def test_a_rule_switched_off_and_on_again_is_worked_out_again(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.svc.backfill()
        self.shop._rules = [rule(enabled=0)]
        self.svc.load()
        self.svc.backfill()
        self.shop.person("b1", price_list_rate=20.0)            # changed while the rule was off: its event did nothing
        self.shop._rules = [rule()]
        self.svc.load()
        self.svc.backfill()
        self.assertEqual(self.shop.at("SELL")[0]["price_list_rate"], "30.00")

    def test_a_source_rows_unit_edited_moves_its_made_row(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        self.shop.person("b1", uom="Box")
        self.event("b1")
        rows = self.shop.at("SELL")
        self.assertEqual([(r["uom"], r["price_list_rate"]) for r in rows], [("Box", "15.00")])
        self.assertTrue(self.svc.reconcile()["clean"])

    def test_a_source_row_given_a_customer_ends_its_made_row(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        self.shop.person("b1", customer="C1")
        self.event("b1")
        self.assertEqual(self.shop.at("SELL")[0]["valid_upto"], str(TODAY - dt.timedelta(days=1)))

    def test_a_made_row_a_person_changed_is_not_ended_when_its_source_goes(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        [t] = self.shop.at("SELL")
        self.shop.person(t["name"], price_list_rate=14.0)
        del self.shop.data["b1"]
        self.event("b1", "item_price.deleted")
        self.assertEqual(self.shop.data[t["name"]]["valid_upto"], None)
        rep = self.svc.reconcile()
        self.assertEqual((rep["differences"], rep["held"][0]["why"]), ([], "its source is gone, but a person changed it: left as it is"))


# ---------------------------------------------------------------------------------------------- 3. chains and loops
class Chain(Base):
    rules = [rule("AB", "BUY", "SELL", factor="1.5"), rule("BC", "SELL", "WHOLESALE", factor="0.9")]

    def test_a_chain_cascades_from_one_event(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        self.assertEqual(self.shop.at("SELL")[0]["price_list_rate"], "15.00")
        self.assertEqual(self.shop.at("WHOLESALE")[0]["price_list_rate"], "13.50")
        self.shop.person("b1", price_list_rate=20.0)
        self.event("b1")
        self.assertEqual(self.shop.at("WHOLESALE")[0]["price_list_rate"], "27.00")


class Loop(Base):
    rules = [rule("AB", "BUY", "SELL"), rule("BA", "SELL", "BUY")]

    def test_a_loop_writes_nothing_and_is_reported(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.event("b1")
        self.assertEqual((self.shop.writes, sorted(r["rule"] for r in self.svc.refused)), ([], ["AB", "BA"]))
        self.assertFalse(self.svc.reconcile()["clean"])


# ---------------------------------------------------------------------------------------------- 4. a deleted source
class Deleted(Chain):
    def test_a_deleted_source_ends_only_the_rows_made_from_it(self):
        self.shop.put("BUY", "A", 10.0, name="b1")
        self.shop.put("BUY", "B", 20.0, name="b2")
        self.event("b1")
        self.event("b2")
        before = {n: dict(r) for n, r in self.shop.data.items()}
        del self.shop.data["b1"]
        self.event("b1", "item_price.deleted")
        y = str(TODAY - dt.timedelta(days=1))
        changed = {n for n, r in self.shop.data.items() if r != before[n]}
        made = {r["name"] for r in self.shop.at("SELL", "A") + self.shop.at("WHOLESALE", "A")}
        self.assertEqual(changed, made)                       # the A rows down the chain, nothing else
        for n in made:
            self.assertEqual((self.shop.data[n]["valid_upto"], self.shop.data[n]["valid_from"]), (y, y))
        self.assertEqual(len(self.shop.data), 5)              # the made rows ended, never deleted (b1 is the one gone)
        self.event("b1", "item_price.deleted")                # again: nothing more
        self.assertEqual(len(self.shop.writes), 6)


# ---------------------------------------------------------------------------------------------- 5. backfill
class Backfill(Base):
    def setUp(self):
        super().setUp()
        for i in range(5):
            self.shop.put("BUY", f"I{i}", 10.0 + i, name=f"b{i}")
        self._page, S.PAGE = S.PAGE, 2

    def tearDown(self):
        S.PAGE = self._page

    def test_a_crash_resumes_at_the_saved_page_and_writes_nothing_twice(self):
        with self.assertRaises(SystemExit):
            self.svc.backfill(crash_after_pages=1)
        self.assertEqual(len(self.shop.writes), 2)
        self.shop.pages.clear()
        self.svc.backfill()
        self.assertEqual(self.shop.pages[0], "b1")             # resumed after the last saved page, not from the start
        self.assertEqual(sorted(w[1] for w in self.shop.writes), sorted({w[1] for w in self.shop.writes}))
        self.assertEqual(len(self.shop.at("SELL", "I4")), 1)
        self.assertEqual(len(self.shop.writes), 5)

    def test_a_done_rule_is_not_run_again_until_its_numbers_change(self):
        self.svc.backfill()
        self.shop.pages.clear()
        self.svc.backfill()
        self.assertEqual(self.shop.pages, [])
        self.shop._rules = [rule(factor="2")]
        self.svc.load()
        self.svc.backfill()
        self.assertEqual(self.shop.at("SELL", "I0")[0]["price_list_rate"], "20.00")


# ---------------------------------------------------------------------------------------------- 6. reconcile
class Reconcile(Base):
    def setUp(self):
        super().setUp()
        for i in range(4):
            self.shop.put("BUY", f"I{i}", 10.0 + i, name=f"b{i}")
        self.shop.put("BUY", "I5", 10.0, name="b5", valid_upto="2026-12-31")
        self.shop.put("BUY", "I6", 10.0, name="b6")
        self.svc.backfill()

    def test_a_clean_list_reads_0(self):
        rep = self.svc.reconcile()
        self.assertEqual((rep["differences"], rep["held"], rep["clean"]), ([], [], True))

    def test_each_planted_fault_is_named(self):
        made = {r["item_code"]: r["name"] for r in self.shop.data.values() if r["price_list"] == "SELL"}
        self.shop.data[made["I0"]]["price_list_rate"] = "99.00"          # a wrong price the service wrote
        del self.shop.data[made["I1"]]                                     # a target price gone
        del self.shop.data["b2"]                                           # a source gone with no event
        self.shop.person(made["I3"], price_list_rate=1.0)                  # a person's change: held, not a difference
        self.shop.put("SELL", "I9", 5.0, name="s9")                        # a person's own price: held
        self.shop.data[self.shop.at("SELL", "I5")[0]["name"]]["valid_upto"] = None                # an end date lost
        self.shop.data[self.shop.at("SELL", "I6")[0]["name"]]["uom"] = "Box"                      # a unit that is not its source's
        rep = self.svc.reconcile()
        whats = sorted((d["item"], d["what"]) for d in rep["differences"])
        self.assertEqual(whats, [("I0", "price differs"), ("I1", "no target price"), ("I2", "its source is gone, and it still sells"),
                                 ("I5", "end date differs"), ("I6", "item or unit differs from its source")])
        self.assertEqual(sorted(h["why"] for h in rep["held"]),
                         ["a price at the target that the service did not make", "changed by a person since the service wrote it"])
        self.assertFalse(rep["clean"])

    def test_reconcile_writes_nothing(self):
        n = len(self.shop.writes)
        del self.shop.data["b2"]
        self.svc.reconcile()
        self.assertEqual(len(self.shop.writes), n)


if __name__ == "__main__":
    unittest.main()
