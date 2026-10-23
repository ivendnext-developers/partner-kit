"""S42's answers, and the calls the bench recorded, against the published contract (``partner_check.v1`` in
``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts")]
import check  # noqa: E402
import optical  # noqa: E402
from test_rules import RX_CL_OLD, TODAY, context, line, rxs  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_opt.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(customer="Walk In"), context([line("X", "Y", -1)], stage="return")):
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])

    def test_every_answer_the_service_gives_holds(self):
        long = "W" * 200
        for rx in ([], rxs(RX_CL_OLD)):
            for code in ("ACUVUE-30", long):
                out = optical.on_check(context([line(code, "Contact lenses", n=500)]), ["Contact lenses"], rx, TODAY)
                self.assertEqual(check.errors("partner_check", "answer", out), [], (code, rx))
        self.assertEqual(check.errors("partner_check", "answer", {"verdict": "allow"}), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "refuse"}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or {}
        self.assertTrue(got.get("check"))
        for ctx in got["check"]:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
