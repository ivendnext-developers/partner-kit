"""S17's answers, against the published partner page contract
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



@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_answers_the_service_sends_hold(self):
        for note in (None, "Delivery TB-00001 booked."):
            body = json.loads(page.submit_body("a" * 32, "TB-00001", note))
            self.assertEqual(check.errors("partner_page", "submit", body), [], note)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"ctx_nonce": "a" * 32, "result": {"discount": 10}}
        self.assertTrue(check.errors("partner_page", "submit", bad))   # the checker is live


if __name__ == "__main__":
    unittest.main()
