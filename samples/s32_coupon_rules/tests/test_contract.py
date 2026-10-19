"""S32's answers, and the calls the bench recorded, against the published contract (``partner_check.v1`` in
``contracts/``, read by ``tools/contracts/check.py``)."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(ROOT / "tools" / "contracts"), str(HERE.parent / "service")]
import check  # noqa: E402
import coupons  # noqa: E402
from test_rules import RECORDS, Counter, context  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_cpn.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(["STAFF15", "WELCOME10"]), context(["WELCOME10"], customer="", group="")):
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])

    def test_every_answer_the_service_gives_holds(self):
        import app
        rules, long = coupons.rules_of(RECORDS), "W" * 200
        longrules = coupons.rules_of([{"coupon": long, "enabled": 1, "first_purchase_only": 1, "customer_group": long}])
        cases = {"allow": coupons.on_check(context(["WELCOME10"]), rules, Counter()),
                 "first": coupons.on_check(context(["WELCOME10"]), rules, Counter({"CUST-1": 1})),
                 "nocust": coupons.on_check(context(["WELCOME10"], customer=""), rules, Counter()),
                 "group": coupons.on_check(context(["STAFF15"]), rules, Counter()),
                 "long": coupons.on_check(context([long]), longrules, Counter()),
                 "key": {"verdict": "refuse", "reason": app.KEY_REFUSED}}
        for name, out in cases.items():
            self.assertEqual(check.errors("partner_check", "answer", out), [], name)

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "refuse"}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
