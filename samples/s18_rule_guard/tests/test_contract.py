"""S18's answers, and the checks the bench recorded, against the published check contract
(``partner_check.v1.schema.json`` in ``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts")]
import check  # noqa: E402
import rule  # noqa: E402
from test_service import RULES, context  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS_SET5") or os.environ.get("BENCH_RUNS", "/nonexistent"), "set5_s18.json")  # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_context_is_a_valid_request(self):
        self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": context()}), [])

    def test_every_answer_the_service_gives_holds(self):
        rules = rule.rules_from(RULES)
        cases = {"allow": context(), "refuse": context(lines=(("WINE-RESERVE", "Wines"),)), "ask": context(grand=600000),
                 "long item": context(lines=(("W" * 140, "Members Lounge"),))}
        for name, ctx in cases.items():
            self.assertEqual(check.errors("partner_check", "answer", rule.decide(ctx, rules)), [], name)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "allow", "reason": "x"}))   # the checker is live

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_checks_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
