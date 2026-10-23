"""S46's answers, and the calls the bench recorded, against the published contract (``partner_check.v1`` in
``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts"), str(HERE.parent / "service")]
import check  # noqa: E402
import payrules  # noqa: E402
from test_rules import RULES, TREE, context  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_pmr.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(group="Talabat", offered=["Cash"]), context(group="", customer=""),
                    context(stage="return")):
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])

    def test_every_answer_the_service_gives_holds(self):
        long = "G" * 200
        longrules = payrules.rules_of([{"customer_group": long, "kind": payrules.ONLY, "mode_of_payment": "X" * 90}])
        cases = {"allow": payrules.on_check(context(group="Retail", offered=["Cash"]), RULES, TREE),
                 "exclude": payrules.on_check(context(group="Talabat"), RULES, TREE),
                 "but": payrules.on_check(context(group="Account customers"), RULES, TREE),
                 "refuse": payrules.on_check(context(group="Talabat", offered=["Cash"]), RULES, TREE),
                 "many": payrules.on_check(context(group="Talabat", offered=["Talabat"] + [f"M{i}" for i in range(21)]),
                                           RULES, TREE),
                 "twenty": payrules.on_check(context(group="Talabat", offered=["Talabat"] + [f"M{i}" for i in range(20)]),
                                             RULES, TREE),
                 "long": payrules.on_check(context(group=long), longrules, {long: (1, 2)})}
        for name, out in cases.items():
            self.assertEqual(check.errors("partner_check", "answer", out), [], name)
        self.assertEqual(cases["exclude"]["verdict"], "allow")
        self.assertEqual(cases["refuse"]["verdict"], "refuse")

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "allow", "exclude_tenders": ["Cash"]}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
