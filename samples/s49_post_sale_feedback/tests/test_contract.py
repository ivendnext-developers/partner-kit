"""S49's answers, and the presses the bench recorded, against the published Desk action contract
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
import feedback as fb  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_psf_scenario.json")   # a recorded bench run, if named


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_service_gives_holds(self):
        many = {"asked": 9999, "stopped": 9999, "no_contact": 9999}
        cases = {"made": fb.press_answer(3, {"asked": 1}, 0, False, []), "none": fb.press_answer(0, {}, 0, False, []),
                 "left": fb.press_answer(400, many, 12, True, ["R was not found."] * 20),
                 "not set up": fb.message(app.NOT_SET_UP, "warning"),
                 "refused": fb.message(app.REFUSED + app.CONNECT_AGAIN, "warning"),
                 "rule": fb.message(fb.rule_of({"name": "R" * 120}), "warning")}
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
