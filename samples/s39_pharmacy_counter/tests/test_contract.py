"""S39's calls and answers against the published contracts (``partner_check.v1`` and ``doccheck.v1`` in ``contracts/``,
read by ``tools/contracts/check.py``): the test calls are requests the shop would send, every refusal the rules can give
is an answer the till and the Desk accept, and the Desk subscriptions' settings are ones the shop saves."""

import json
import os
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE), str(HERE.parent / "service"), str(ROOT / "tools" / "contracts")]
import check  # noqa: E402
import rxrules  # noqa: E402
from test_rules import line, rule, rx, shop, ctx, decide  # noqa: E402
from test_service import desk_body, till_body  # noqa: E402

MANIFEST = json.loads((HERE.parent / "manifest.json").read_text())
RUN = os.environ.get("BENCH_RUN", "/nonexistent")     # a recorded bench scenario (its "received" check contexts)


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_the_test_calls_are_valid_requests(self):
        for body in (till_body([("AMOX", "Rx", 21)], rx="RX1"),
                     till_body([("AMOX", "Rx", -21)], stage="return", return_of="INV-1")):
            self.assertEqual(check.errors("partner_check", "request", body), [])
        body = desk_body("Sales Invoice", "SI-1", [{"item_code": "AMOX", "item_group": "Rx", "stock_qty": 21000}], rx="RX1")
        self.assertEqual(check.errors("doccheck", "request", body), [])

    def test_every_refusal_the_rules_give_holds_at_the_till_and_on_the_desk(self):
        long = "X" * 200
        answers = []
        c = ctx([line(long, 21)])
        answers.append(decide(c, shop(c, [rule("POM")])))
        c = ctx([line("A", 21)], details={"Rx Number": long})
        answers.append(decide(c, shop(c, [rule("POM")])))
        c = ctx([line("A", -21)], stage="return")
        answers.append(decide(c, shop(c, [rule("POM")])))
        c = ctx([line("A", 21)], details={"Rx Number": "RX1"})
        import datetime
        answers.append(decide(c, shop(c, [rule("POM")], [rx("RX1", "A", 21)],
                                      pharmacist={"active": True, "valid_until": datetime.date(2001, 1, 1)})))
        answers.append(decide(c, shop(c, [rule("POM")], [rx("RX1", "A", 21)])))
        for out in answers:
            out = {k: v for k, v in out.items() if k != "record"}
            self.assertEqual(check.errors("partner_check", "answer", out), [], out)
            self.assertEqual(check.errors("doccheck", "answer", out), [], out)
            self.assertLessEqual(len(out.get("reason", "")), rxrules.TEXT_MAX)

    def test_the_desk_subscriptions_settings_are_ones_the_shop_saves(self):
        for s in MANIFEST["extension_subscriptions"]:
            if s["point"] == "doccheck":
                self.assertEqual(check.errors("doccheck", "settings", s["settings"]), [], s["key"])

    @unittest.skipUnless(os.path.exists(RUN), "no bench run recorded yet")
    def test_the_calls_the_bench_sent_hold_and_read_as_the_service_reads_them(self):
        got = (json.load(open(RUN)).get("received") or {}).get("check") or []
        self.assertTrue(got)
        for c in got:
            self.assertEqual(check.errors("partner_check", "request", {"point": "check/1", "context": c}), [])
            rxrules.sale_context({"point": "check/1", "context": c})      # the service's own shape check takes it

    def test_a_bad_answer_is_caught_by_the_contract(self):        # the checker is live
        self.assertTrue(check.errors("partner_check", "answer", {"verdict": "refuse"}))
        self.assertTrue(check.errors("doccheck", "answer", {"verdict": "fill"}))


if __name__ == "__main__":
    unittest.main()
