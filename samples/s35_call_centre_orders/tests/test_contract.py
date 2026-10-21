"""S35's answers, and the presses the bench recorded, against the published Desk action contract
(``desk_action.v1.schema.json`` in ``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), os.path.join(ROOT, "tools", "contracts")]
import app  # noqa: E402
import check  # noqa: E402
import route  # noqa: E402
from test_service import order  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_cco_scenario.json")   # a recorded bench run, if named


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_service_gives_holds(self):
        long = "S" * 140
        cases = {"sent": route.sent(order(), "Maadi Store - S", "Maadi"),
                 "sent from above": route.sent(order(territory="Heliopolis"), "Cairo Store - S", "Cairo"),
                 "sent, long names": route.sent(order(territory=long), long, long),
                 "already": route.already("Maadi Store - S", "Maadi"), "already, long": route.already(long, long),
                 "not set up": app._warning(app.NOT_SET_UP), "refused": app._warning(app.REFUSED + app.CONNECT_AGAIN),
                 "no territory": app._warning(app.NO_TERRITORY), "submitted": app._warning(app.SUBMITTED),
                 "gone": app._warning(app.GONE), "changed": app._warning(app.CHANGED),
                 "no store": app._warning(app.no_store(long)), "not taken": app._warning(app.not_taken(long))}
        for name, value in cases.items():
            self.assertEqual(check.errors("desk_action", "answer", value), [], name)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"message": {"title": "x", "body": "y" * 281, "level": "success"}, "refresh": True}
        self.assertTrue(check.errors("desk_action", "answer", bad))   # a body over 280: the checker is live

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_presses_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("desk_action", "request", {"point": "desk_action/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
