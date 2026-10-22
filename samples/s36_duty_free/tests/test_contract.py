"""S36's answers, and the calls the bench recorded, against the published contract (``partner_check.v1`` in
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
import dutyfree  # noqa: E402
from test_rules import GROUPS, SETTINGS, TODAY, bcbp, context, leg, line  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_dfa.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(pass_text=""), context([line("X", "Whisky", -1)], stage="return")):
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])

    def test_every_answer_the_service_gives_holds(self):
        import app
        s, g = dutyfree.settings_of(SETTINGS), dutyfree.groups_of(GROUPS, "PP DFA")
        long = dutyfree.groups_of([{"name": "S" * 200, "lft": 1, "rgt": 2, "pp_dfa_allowance": 1, "pp_dfa_unit": "u" * 90}], "PP DFA")
        reasons = [dutyfree.NO_PASS, dutyfree.UNREADABLE, dutyfree.OTHER_DAY, dutyfree.OTHER_DAY_ARRIVING, app.KEY_REFUSED,
                   dutyfree.pass_problem(bcbp(leg("LHR", "JFK")), s, TODAY),
                   dutyfree.pass_problem(bcbp(leg("LHR", "JFK")), dutyfree.settings_of(dict(SETTINGS, direction="arriving")), TODAY),
                   dutyfree.over_allowance([("Whisky", 9.0)], g, {"Spirits"}),
                   dutyfree.over_allowance([("S" * 200, 9.0)], long, set(long))]
        for reason in reasons:
            self.assertEqual(check.errors("partner_check", "answer", {"verdict": "refuse", "reason": reason}), [], reason)
        self.assertEqual(check.errors("partner_check", "answer", {"verdict": "allow"}), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "refuse"}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
