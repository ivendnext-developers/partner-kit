"""S1's answers against the published remote till key contract (``remote_till_key.v1.schema.json`` in ``contracts/``, read by
``tools/contracts/check.py``). Stdlib only:  python3 -m unittest discover -s samples/s1_warranty/tests -p 'test_contract.py' -v"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), HERE, os.path.join(ROOT, "tools", "contracts")]
import cases  # noqa: E402
import check  # noqa: E402
import core  # noqa: E402
from test_core import TERMS  # noqa: E402


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_core_gives_holds(self):
        for name, context in cases.contexts().items():
            with self.subTest(name):
                self.assertEqual(check.errors("remote_till_key", "answer", core.warranty_answer(context, TERMS)), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):
        self.assertTrue(check.errors("remote_till_key", "answer", {"discount": 10}))   # the checker is live


if __name__ == "__main__":
    unittest.main()
