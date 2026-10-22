"""S37's answers, and the calls the bench recorded, against the published contracts (``partner_check.v1`` and
``partner_capture.v1`` in ``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts")]
import agecheck  # noqa: E402
import check  # noqa: E402
from test_rules import SETTINGS, TODAY, context, line, scan  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_age.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(checked="18 or over"), context([line("X", "Y", -1)], stage="return")):
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])
        for ref in ("sale-1", ""):
            self.assertEqual(check.errors("partner_capture", "scan_request", {"point": "capture/1", "context": scan(sale_ref=ref)}), [])

    def test_every_answer_the_service_gives_holds(self):
        long = "W" * 200
        for look in (0, 25, 120):
            for code, age in (("WHISKY", 18), (long, 120)):
                out = agecheck.on_scan(scan(code), age, agecheck.settings_of(dict(SETTINGS, look_under=look)), TODAY, "PP AGE")
                self.assertEqual(check.errors("partner_capture", "scan_answer", out), [], (look, code))
        self.assertEqual(check.errors("partner_capture", "scan_answer", {"verdict": "allow"}), [])
        for checked in (0, 18):
            for code in ("WHISKY", long):
                out = agecheck.on_check(context([line(code, "Vapes", n=999)]), [21], checked)
                self.assertEqual(check.errors("partner_check", "answer", out), [], (checked, code))
        self.assertEqual(check.errors("partner_check", "answer", {"verdict": "allow"}), [])

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "refuse"}))
        self.assertTrue(check.errors("partner_capture", "scan_answer", {"verdict": "notice"}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or {}
        self.assertTrue(got.get("check") and got.get("scan"))
        for ctx in got["check"]:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])
        for ctx in got["scan"]:
            self.assertEqual(check.errors("partner_capture", "scan_request", {"point": "capture/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
