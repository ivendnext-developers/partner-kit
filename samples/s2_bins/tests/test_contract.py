"""S2's answers against the published remote till key contract (``remote_till_key.v1.schema.json`` in ``contracts/``, read by
``tools/contracts/check.py``). Stdlib only:  python3 -m unittest discover -s samples/s2_bins/tests -p 'test_contract.py' -v"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), HERE, os.path.join(ROOT, "tools", "contracts")]
import check  # noqa: E402
import core  # noqa: E402
from test_core import ROWS, ctx  # noqa: E402


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_core_gives_holds(self):
        cases = {"on the floor": ctx("A"), "back room only": ctx("B"), "empty bin and unknown item": ctx("A", "C", "Z"),
                 "empty sale": ctx(), "sixty lines": ctx(*[f"ITEM-{i:03d}-WITH-A-LONG-CODE" for i in range(60)])}
        for name, context in cases.items():
            with self.subTest(name):
                self.assertEqual(check.errors("remote_till_key", "answer", core.where_answer(context, ROWS)), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):
        self.assertTrue(check.errors("remote_till_key", "answer", {"discount": 10}))   # the checker is live


if __name__ == "__main__":
    unittest.main()
