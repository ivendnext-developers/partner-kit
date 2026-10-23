"""S48's answers, and the calls the bench recorded, against the published contract (``partner_capture.v1`` in
``contracts/``, read by ``tools/contracts/check.py``): the select, the verify, and every answer either one gives."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts"), str(HERE.parent / "service")]
import check  # noqa: E402
import codecheck  # noqa: E402
from test_rules import RULES, TREE, code_ctx, context  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_ccc.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(group="", phone=""), context(group="Trade")):
            self.assertEqual(check.errors("partner_capture", "select_request", {"point": "capture/1", "context": ctx}), [])
        self.assertEqual(check.errors("partner_capture", "verify_request", {"point": "capture/1", "context": code_ctx()}), [])

    def test_every_select_answer_holds(self):
        long = "G" * 200
        longrules = codecheck.rules_of([{"customer_group": long, "ask": "Ask for a code", "words": "w" * 300}])
        cases = {"challenge": codecheck.on_select(context(group="Members"), RULES, TREE, recent=False),
                 "words": codecheck.on_select(context(group="Trade"), RULES, TREE, recent=False),
                 "allow": codecheck.on_select(context(group="Retail"), RULES, TREE, recent=False),
                 "recent": codecheck.on_select(context(group="Members"), RULES, TREE, recent=True),
                 "no mobile": codecheck.on_select(context(group="Members", phone=""), RULES, TREE, recent=False),
                 "long": codecheck.on_select(context(group=long), longrules, {long: (1, 2)}, recent=False),
                 "long refuse": codecheck.on_select(context(group=long, phone=""), longrules, {long: (1, 2)}, recent=False)}
        for name, out in cases.items():
            self.assertEqual(check.errors("partner_capture", "select_answer", out), [], name)
        self.assertEqual(cases["challenge"]["verdict"], "challenge")
        self.assertEqual(cases["no mobile"]["verdict"], "refuse")

    def test_every_verify_answer_holds(self):
        rec = {"code": "482913", "status": "Sent", "sent_at": 1000}
        for out in (codecheck.on_verify(code_ctx(), rec, 1001), codecheck.on_verify(code_ctx("000000"), rec, 1001),
                    codecheck.on_verify(code_ctx(), None, 1001)):
            self.assertEqual(check.errors("partner_capture", "verify_answer", out), [], out)

    def test_a_code_new_code_makes_is_one_the_till_accepts(self):
        for _ in range(50):
            self.assertEqual(check.errors("partner_capture", "verify_request",
                                          {"point": "capture/1", "context": code_ctx(codecheck.new_code())}), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_capture", "select_answer", {"verdict": "challenge", "prompt": "x", "length": 9}))
        self.assertTrue(check.errors("partner_capture", "verify_answer", {"verdict": "refuse"}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            kind = "verify_request" if ctx.get("event") == "verify" else "select_request"
            self.assertEqual(check.errors("partner_capture", kind, {"point": "capture/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
