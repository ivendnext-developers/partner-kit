"""S45's answers, and the presses the bench recorded, against the published Desk action contract
(``desk_action.v1.schema.json`` in ``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), os.path.join(ROOT, "tools", "contracts")]
import app  # noqa: E402
import backoffice as bo  # noqa: E402
import check  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "ho_k4_scenario.json")   # a recorded bench run, if named


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_service_gives_holds(self):
        every = {"issued": 3, "short": 2, "refused": 1, "nothing": 4, "sales": 300}
        cases = {"issued": app.Service._answer({"issued": 1, "short": 0, "refused": 0, "nothing": 0, "sales": 3}),
                 "every outcome, more left": app.Service._answer(every, left=True),
                 "nothing": app.Service._answer({"issued": 0, "short": 0, "refused": 0, "nothing": 0, "sales": 0}),
                 "not set up": app._warning(app.NOT_SET_UP), "refused": app._warning(app.REFUSED + app.CONNECT_AGAIN),
                 "busy": app._warning(app.BUSY), "no start": app._warning(app.NO_START),
                 "long": bo.message(app.APP_NAME, "x " * 400, "warning", refresh=False),
                 "a check to open": dict(bo.message(app.APP_NAME, "2 dishes miss an allergen of their recipe.", "warning",
                                                    refresh=False),
                                         open_record={"doctype": "PP RBO Allergen Check", "name": "RBO-ALC-00001"})}
        for name, value in cases.items():
            self.assertEqual(check.errors("desk_action", "answer", value), [], name)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"message": {"title": "x", "body": "y" * 281, "level": "success"}, "refresh": True}
        self.assertTrue(check.errors("desk_action", "answer", bad))   # a body over 280: the checker is live

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_presses_the_bench_sent_hold(self):
        with open(RUN) as f:
            got = json.load(f).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("desk_action", "request", {"point": "desk_action/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
