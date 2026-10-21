"""S23's answers, and the calls the bench recorded, against the published contracts (``partner_check.v1`` and
``partner_capture.v1`` in ``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts")]
import check  # noqa: E402
import guard  # noqa: E402
from test_guard import SETTINGS, context, line, scan  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_tgr.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": context()}), [])
        self.assertEqual(check.errors("partner_capture", "scan_request", {"point": "capture/1", "context": scan()}), [])

    def test_every_answer_the_service_gives_holds(self):
        rules = guard.settings_of(SETTINGS)
        ask = guard.settings_of(dict(SETTINGS, approval_answer="ask"))
        long = "W" * 200
        cases = {"allow": (context(), rules), "price": (context([line(1, "PEN-01", rate=1)]), rules),
                 "qty": (context([line(1, long, qty=99, rate=10)]), rules),
                 "approve": (context([line(1, "TV", rate=900000)]), rules), "ask": (context([line(1, "TV", rate=900000)]), ask)}
        for name, (ctx, r) in cases.items():
            self.assertEqual(check.errors("partner_check", "answer", guard.on_check(ctx, r)), [], name)
        for code in ("PEN-01", long):
            self.assertEqual(check.errors("partner_capture", "scan_answer", guard.on_scan(scan(code), rules)), [], code)
        later, sooner = ("2026-12-01", "B-" + long), ("2026-11-02", "B-SOON")
        for ctx in (scan(long), dict(scan(long), line=dict(scan(long)["line"], batch_no="B-" + long))):
            out = guard.on_scan_shelf(ctx, [later, sooner])
            self.assertEqual((out["verdict"], check.errors("partner_capture", "scan_answer", out)), ("notice", []))

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "approve"}))
        self.assertTrue(check.errors("partner_capture", "scan_answer", {"verdict": "confirm"}))

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
