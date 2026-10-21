"""S20's answers against the published capture contract
(``partner_capture.v1.schema.json`` in ``contracts/``, read by ``tools/contracts/check.py``).
The service keeps no record of the calls it received, so no recorded bench call is replayed here (S18's test does)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts")]
import capture  # noqa: E402
import check  # noqa: E402
from test_service import CONF, customer_ctx, qty_ctx, scan_ctx, verify_ctx  # noqa: E402

REQUESTS = {"scan": "scan_request", "customer_add": "customer_request", "verify": "verify_request",
            "qty_change": "qty_request"}


def wrap(ctx):
    return {"point": "capture/1", "context": ctx}


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (scan_ctx(), customer_ctx(), verify_ctx("123456"), qty_ctx(4)):
            self.assertEqual(check.errors("partner_capture", REQUESTS[ctx["event"]], wrap(ctx)), [], ctx["event"])

    def test_every_answer_the_service_gives_holds(self):
        conf = capture.settings_from(CONF)
        codes, sent = capture.Codes(), []
        self.assertEqual(check.errors("partner_capture", "scan_answer", capture.on_scan(scan_ctx(), conf)), [])
        for q in (2, 4, 9):
            self.assertEqual(check.errors("partner_capture", "qty_answer", capture.on_qty(qty_ctx(q, answered=1), conf)), [], q)
        for phone in ("", "+971500000000", "+971501234567"):
            out = capture.on_customer(customer_ctx(phone=phone), conf, codes, lambda p, c: sent.append(c))
            self.assertEqual(check.errors("partner_capture", "customer_answer", out), [], phone)
        for code in ("000000" if sent[0] != "000000" else "111111", sent[0], "123456"):
            out = capture.on_verify(verify_ctx(code), codes)
            self.assertEqual(check.errors("partner_capture", "verify_answer", out), [], out)

    def test_a_bad_answer_is_caught_by_the_contract(self):
        bad = {"verdict": "allow", "line_attributes": [{"name": "Warranty ref"}]}     # a row without its value
        self.assertTrue(check.errors("partner_capture", "scan_answer", bad))          # the checker is live


if __name__ == "__main__":
    unittest.main()
