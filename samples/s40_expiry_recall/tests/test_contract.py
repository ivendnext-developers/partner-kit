"""S40's answers against the published contracts (``desk_action.v1`` and ``doccheck.v1`` in ``contracts/``, read by
``tools/contracts/check.py``), and the calls the bench recorded, if a run is named."""

import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [HERE, os.path.join(ROOT, "tools", "contracts")]
import fakeshop  # noqa: E402,F401  (puts the sample on the path)
import app  # noqa: E402
import check  # noqa: E402
import recall  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "ph_b2_scenario.json")


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_press_answer_holds(self):
        every = {k: 3 for k in recall.OUTCOME_WORDS}
        cases = {"blocked": recall.block_answer({"block": 1}, 2, 3, "Consumer"),
                 "every outcome": recall.block_answer(every, 120, 9999, "Wholesale"),
                 "worklist": recall.message("Worklist", "x" * 400), "not set up": app._warning(app.NOT_SET_UP),
                 "refused": app._warning(app.REFUSED + app.CONNECT_AGAIN), "no settings": app._warning(app.NO_SETTINGS)}
        for name, value in cases.items():
            self.assertEqual(check.errors("desk_action", "answer", value), [], name)

    def test_every_check_answer_holds(self):
        long = ["Row 12: lot " + "X" * 200 + " has 3 days left, under 180."] * 4
        cases = {"allow": {"verdict": "allow"}, "refuse": recall.receipt_answer(long, False),
                 "fill": recall.receipt_answer(long, True), "disposal": recall.disposal_answer(long),
                 "app refused": {"verdict": "refuse", "reason": recall.fit(app.CHECK_REFUSED)}}
        for name, value in cases.items():
            self.assertEqual(check.errors("doccheck", "answer", value), [], name)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        self.assertTrue(check.errors("doccheck", "answer", {"verdict": "flag"}))       # no flag in the vocabulary
        self.assertTrue(check.errors("desk_action", "answer", recall.message("t", "b") | {"open_page": "/x"}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        with open(RUN) as f:
            got = json.load(f).get("received") or []
        self.assertTrue(got)
        for r in got:
            point = "desk_action" if r["sub"] in ("block", "worklist") else "doccheck"
            self.assertEqual(check.errors(point, "request", {"point": f"{point}/1", "context": r["context"]}), [], r["sub"])


if __name__ == "__main__":
    unittest.main()
