"""S16's answers, and the presses the bench recorded, against the published Desk action contract
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

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "s10b_s16.json")   # a recorded test-bench run, if one is named


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def tasks(self, n):
        rec = {"name": "SO-1", "fields": {"customer": "C", "set_warehouse": "W", "delivery_date": "2026-10-09",
                                          "items": [{"item_code": "A", "qty": 1000, "warehouse": "W"}]}}
        return [route.plan(dict(rec, name=f"SO-{i}"), {"picker": "p@x", "priority": "Normal"}, "k" * 12) for i in range(n)]

    def test_every_answer_the_service_gives_holds(self):
        cases = {"open": route.answer(self.tasks(1), ["PCK-00001"]),
                 "refresh": route.answer(self.tasks(1), ["PCK-00001"], "refresh"),
                 "missing": route.answer(self.tasks(1), [], "missing"),
                 "bulk": route.answer(self.tasks(3), ["PCK-1", "PCK-2", "PCK-3"]),
                 "not set up": app._warning(app.NOT_SET_UP), "refused": app._warning(app.REFUSED + app.CONNECT_AGAIN),
                 "too many": app._warning(app.TOO_MANY)}
        for name, value in cases.items():
            self.assertEqual(check.errors("desk_action", "answer", value), [], name)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"message": {"title": "x", "body": "y", "level": "success"}, "refresh": True,
               "open_record": {"doctype": route.TASK, "name": "PCK-1"}}
        self.assertTrue(check.errors("desk_action", "answer", bad))   # two next steps: the checker is live

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_presses_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("desk_action", "request", {"point": "desk_action/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
