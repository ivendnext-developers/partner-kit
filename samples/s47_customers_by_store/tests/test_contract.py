"""S47's answers, and the calls the bench recorded, against the published contract (``partner_capture.v1`` in
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
import storerules  # noqa: E402
from test_rules import RULES, TREE, context  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_cbs.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(group="", store="", profile=""), context(group="Trade accounts", store="Bulawayo - CL")):
            self.assertEqual(check.errors("partner_capture", "select_request", {"point": "capture/1", "context": ctx}), [])

    def test_every_answer_the_service_gives_holds(self):
        long = "G" * 200
        longrules = storerules.rules_of([{"customer_group": long, "store": "X" * 140}])
        cases = {"allow": storerules.on_select(context(group="Trade accounts"), RULES, TREE),
                 "none": storerules.on_select(context(group="Retail"), RULES, TREE),
                 "refuse": storerules.on_select(context(group="Trade accounts", store="Bulawayo - CL"), RULES, TREE),
                 "nowhere": storerules.on_select(context(group="Blocked"), RULES, TREE),
                 "words": storerules.on_select(context(group="Staff"), RULES, TREE),
                 "long": storerules.on_select(context(group=long, store="Y"), longrules, {long: (1, 2)})}
        for name, out in cases.items():
            self.assertEqual(check.errors("partner_capture", "select_answer", out), [], name)
        self.assertEqual(cases["allow"], {"verdict": "allow"})
        self.assertEqual(cases["refuse"]["verdict"], "refuse")

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_capture", "select_answer", {"verdict": "refuse"}))
        self.assertTrue(check.errors("partner_capture", "select_answer", {"verdict": "refuse", "reason": "x" * 141}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("partner_capture", "select_request", {"point": "capture/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
