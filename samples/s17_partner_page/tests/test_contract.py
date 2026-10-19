"""S17's answers, and the contexts the bench minted, against the published partner page contract
(``partner_page.v1.schema.json`` in ``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(ROOT, "tools", "contracts")]
import check  # noqa: E402
import page  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "s10b_s17.json")   # a recorded test-bench run, if one is named


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_answers_the_service_sends_hold(self):
        for note in (None, "Delivery TB-00001 booked."):
            body = json.loads(page.submit_body("a" * 32, "TB-00001", note))
            self.assertEqual(check.errors("partner_page", "submit", body), [], note)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"ctx_nonce": "a" * 32, "result": {"discount": 10}}
        self.assertTrue(check.errors("partner_page", "submit", bad))   # the checker is live

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_contexts_the_bench_minted_hold(self):
        got = json.load(open(RUN)).get("opened") or []
        self.assertTrue(got)
        for payload in got:
            self.assertEqual(check.errors("partner_page", "context", payload), [])


if __name__ == "__main__":
    unittest.main()
