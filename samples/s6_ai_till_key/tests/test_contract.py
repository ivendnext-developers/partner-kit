"""S6's answers against the published remote till key contract (``remote_till_key.v1.schema.json`` in ``contracts/``, read by
``tools/contracts/check.py``). Stdlib only:  python3 -m unittest discover -s samples/s6_ai_till_key/tests -p 'test_contract.py' -v"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), HERE, os.path.join(ROOT, "tools", "contracts")]
import check  # noqa: E402
import core  # noqa: E402
from test_core import CONTEXT  # noqa: E402

REPLIES = {"plain": "Suggest the leather case; it protects the phone.",
           "control characters and spaces": "Suggest\x00 the   case\n\tfor the phone.",
           "longer than the till allows": "Suggest a care kit for the leather case. " * 40}


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_core_gives_holds(self):
        for name, reply in REPLIES.items():
            with self.subTest(name):
                self.assertEqual(check.errors("remote_till_key", "answer", core.answer(CONTEXT, lambda prompt, r=reply: r)), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):
        self.assertTrue(check.errors("remote_till_key", "answer", {"discount": 10}))   # the checker is live


if __name__ == "__main__":
    unittest.main()
