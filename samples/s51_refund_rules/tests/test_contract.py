"""S51's answers, and the calls the bench recorded, against the published contract (``partner_check.v1`` in
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
import refunds  # noqa: E402
from test_rules import CARD, CASH, VOUCHER, context, line, rows, settings  # noqa: E402

RUN = os.path.join(os.environ.get("BENCH_RUNS", "/nonexistent"), "appf_rfr.json")    # a recorded bench run


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for ctx in (context(), context(channel="none"), context(channel="order"), context(channel="layaway"),
                    context(stage="sale", lines=[line(qty=1)])):
            if ctx["stage"] == "sale":
                ctx.pop("return_of", None)
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])

    def test_every_answer_the_service_gives_holds(self):
        cases = {"allow": refunds.on_check(context(paid_by=("Cash", "Credit Card", "Store Credit", "Online Refund")),
                                           settings()),
                 "exclude": refunds.on_check(context(), settings()),
                 "none": refunds.on_check(context(paid_by=(VOUCHER,), offered=[CASH, CARD]), settings()),
                 "no sale": refunds.on_check(context(channel="none"), settings(without_sale=rows(CASH))),
                 "no sale none": refunds.on_check(context(channel="none", offered=[CARD]),
                                                  settings(without_sale=rows(VOUCHER), store_credit="")),
                 "many": refunds.on_check(context(offered=[f"M{i}" for i in range(25)] + [CARD]), settings())}
        for name, out in cases.items():
            self.assertEqual(check.errors("partner_check", "answer", out), [], name)
        self.assertEqual(cases["allow"], {"verdict": "allow"})
        self.assertEqual(cases["exclude"]["verdict"], "allow")
        self.assertEqual(cases["none"]["verdict"], "refuse")

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "allow", "exclude_tenders": ["Cash"]}))

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold(self):
        got = json.load(open(RUN)).get("received") or []
        self.assertTrue(got)
        for ctx in got:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": ctx}), [])


if __name__ == "__main__":
    unittest.main()
