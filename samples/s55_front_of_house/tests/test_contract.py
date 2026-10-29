"""S55's answers against the published Desk action contract, and the call that opens a check against the open-check
contract (``desk_action.v1.schema.json``, ``open_check.v1.schema.json`` in ``contracts/``, read by
``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), os.path.join(ROOT, "tools", "contracts")]
import app  # noqa: E402
import check  # noqa: E402
import foh  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "ho_k2_scenario.json")   # a recorded bench run, if named


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_service_gives_holds(self):
        cases = {"booked": foh.message(app.APP_NAME, "FOH-RES-00042 is booked: Table 12 is held for 4 from 19:00 to 20:30."),
                 "not booked": app._warning("Not booked: Table 12 is booked from 19:30 to 21:00.", refresh=True),
                 "not set up": app._warning(app.NOT_SET_UP), "refused": app._warning(app.REFUSED + app.CONNECT_AGAIN),
                 "busy": app._warning(app.BUSY), "long": foh.message(app.APP_NAME, "x " * 400, "warning", refresh=False)}
        for name, value in cases.items():
            self.assertEqual(check.errors("desk_action", "answer", value), [], name)

    def test_the_call_that_opens_a_check_holds(self):
        req = foh.seat_request("Bistro - BC", "Bistro R1", "6f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a", "FP-T12",
                               "FOH-RES-00042", 4, 50)
        self.assertEqual(check.errors("open_check", "open_request", req), [])
        self.assertTrue(check.errors("open_check", "open_request", dict(req, source="Front Of House!")))   # live

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"message": {"title": "x", "body": "y" * 281, "level": "success"}, "refresh": True}
        self.assertTrue(check.errors("desk_action", "answer", bad))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_presses_the_bench_sent_hold(self):
        with open(RUN) as f:
            got = json.load(f).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("desk_action", "request", {"point": "desk_action/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
