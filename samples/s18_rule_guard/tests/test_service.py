"""S18's laptop tests: the rule (``rule.decide``) and the real service on a local port, called exactly as the shop calls
it (base64 HMAC-SHA256 of ``<timestamp>.<body>``, the body sorted-key compact JSON).

    python3 -m unittest discover -s samples/s18_rule_guard/tests -p 'test_*.py'

On our test bench the till's own Pay was pressed through the real check; these prove the service's own duties fast,
and are what the mutation canary turns RED."""

import base64
import copy
import hashlib
import hmac
import json
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service")]
import app  # noqa: E402
import rule  # noqa: E402

SECRET = "s18-test-secret"
RULES = {"PP_MEMBERS_ONLY_ITEMS": "WINE-RESERVE", "PP_MEMBERS_ONLY_GROUPS": "Members Lounge",
         "PP_MEMBER_GROUPS": "Club Members, Gold", "PP_ASK_ABOVE": "5000"}


def context(lines=(("BREAD", "Bakery"),), group="Retail", grand=1250, stage="sale", exp=2, currency="AED"):
    return {"v": 1, "point": "check", "stage": stage, "currency_exponent": exp, "sale_ref": "s-1", "store": "Main - S",
            "pos_profile": "Mall", "company": "Shop", "currency": currency, "lang": "en", "operator": "c@shop.example",
            "customer": "CUST-1", "customer_group": group, "price_list": "Standard Selling", "coupon_codes": [],
            "sale_attributes": [],
            "lines": [{"line_no": i + 1, "item_code": c, "item_group": g, "qty_milli": 1000, "uom": "Nos",
                       "rate_minor": grand, "amount_minor": grand, "discount_minor": 0, "line_attributes": []}
                      for i, (c, g) in enumerate(lines)],
            "totals": {"net_minor": grand, "tax_minor": 0, "discount_minor": 0, "grand_minor": grand},
            "offered_tenders": ["Cash", "Credit Card"]}


def body(ctx=None):
    return json.dumps({"point": "check/1", "context": ctx or context()}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=SECRET, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}


class RuleTest(unittest.TestCase):
    rules = rule.rules_from(RULES)

    def test_an_ordinary_sale_is_allowed(self):
        self.assertEqual(rule.decide(context(), self.rules), {"verdict": "allow"})

    def test_a_members_only_item_without_a_member_is_refused_in_the_partners_words(self):
        out = rule.decide(context(lines=(("BREAD", "Bakery"), ("WINE-RESERVE", "Wines"))), self.rules)
        self.assertEqual(out, {"verdict": "refuse",
                               "reason": "WINE-RESERVE is for members only. Add the member's customer to the sale first."})

    def test_a_members_only_group_counts_too(self):
        self.assertEqual(rule.decide(context(lines=(("CIGAR-1", "Members Lounge"),)), self.rules)["verdict"], "refuse")

    def test_a_member_buys_it(self):
        ctx = context(lines=(("WINE-RESERVE", "Wines"),), group="Gold")
        self.assertEqual(rule.decide(ctx, self.rules), {"verdict": "allow"})

    def test_at_the_id_limit_the_cashier_is_asked(self):
        out = rule.decide(context(grand=500000), self.rules)
        self.assertEqual(out, {"verdict": "ask", "question": "This sale is 5,000.00 AED or more. Has the customer shown ID?"})
        self.assertEqual(rule.decide(context(grand=499999), self.rules), {"verdict": "allow"})

    def test_the_limit_reads_the_currencys_own_digits(self):
        self.assertEqual(rule.decide(context(grand=5000000, exp=3, currency="KWD"), self.rules)["verdict"], "ask")
        self.assertEqual(rule.decide(context(grand=4999999, exp=3, currency="KWD"), self.rules)["verdict"], "allow")
        self.assertEqual(rule.decide(context(grand=5000, exp=0, currency="JPY"), self.rules)["verdict"], "ask")

    def test_a_refusal_wins_over_a_question(self):
        out = rule.decide(context(lines=(("WINE-RESERVE", "Wines"),), grand=900000), self.rules)
        self.assertEqual(out["verdict"], "refuse")

    def test_no_limit_set_never_asks(self):
        rules = rule.rules_from({**RULES, "PP_ASK_ABOVE": ""})
        self.assertEqual(rule.decide(context(grand=10 ** 9), rules), {"verdict": "allow"})

    def test_what_a_return_takes_back_is_never_guarded(self):
        ctx = context(lines=(("WINE-RESERVE", "Wines"),), stage="return", grand=-10 ** 9)
        ctx["lines"][0]["qty_milli"] = -1000          # a returned line: its quantity is negative (the contract's sample)
        self.assertEqual(rule.decide(ctx, self.rules), {"verdict": "allow"})

    def test_an_item_handed_back_inside_a_sale_is_not_judged(self):
        ctx = context(lines=(("BREAD", "Bakery"), ("WINE-RESERVE", "Wines")))
        ctx["lines"][1]["qty_milli"] = -1000          # a members-only item handed back on the same sale
        self.assertEqual(rule.decide(ctx, self.rules), {"verdict": "allow"})

    def test_an_item_a_return_sells_is_judged_as_a_sale_with_no_id_question(self):
        ctx = context(lines=(("BREAD", "Bakery"), ("WINE-RESERVE", "Wines")), stage="return", grand=10 ** 9)
        ctx["lines"][0]["qty_milli"] = -1000          # an exchange rung without its sale: one line back, one sold
        self.assertEqual(rule.decide(ctx, self.rules)["verdict"], "refuse")
        ctx["customer_group"] = "Gold"                # a member: allowed, and never asked for ID on a return
        self.assertEqual(rule.decide(ctx, self.rules), {"verdict": "allow"})

    def test_every_sentence_is_plain_and_fits(self):
        long = "X" * 140 + "<b>"
        for out in (rule.decide(context(lines=((long, "Members Lounge"),)), self.rules),
                    rule.decide(context(grand=10 ** 12), rule.rules_from({**RULES, "PP_ASK_ABOVE": "9999999999"}))):
            text = out.get("reason") or out.get("question")
            self.assertTrue(1 <= len(text) <= rule.TEXT_MAX, text)
            self.assertFalse({"<", ">"} & set(text), text)

    def test_an_item_code_carrying_markup_is_shown_without_it(self):
        rules = rule.rules_from({**RULES, "PP_MEMBERS_ONLY_ITEMS": "<b>WINE</b>"})
        out = rule.decide(context(lines=(("<b>WINE</b>", "Wines"),)), rules)
        self.assertEqual(out["reason"], "bWINE/b is for members only. Add the member's customer to the sale first.")

    def test_a_context_it_cannot_read_is_refused(self):
        for bad in ({"point": "check/2", "context": context()}, {"point": "check/1", "context": {"v": 2}},
                    {"point": "check/1", "context": {**context(), "totals": {"grand_minor": 1.5}}},
                    {"point": "check/1", "context": {**context(), "lines": [{**context()["lines"][0], "qty_milli": 1000.0}]}}):
            with self.assertRaises(ValueError):
                rule.context_of(bad)


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.svc = app.Service({"PP_POINT_SECRET": SECRET, **RULES})
        self.srv = app.ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(self.svc))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}/rgd/check"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def post(self, raw, headers, url=None):
        req = urllib.request.Request(url or self.url, data=raw, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"{}")

    def test_the_three_answers_over_the_wire(self):
        cases = {"allow": context(), "refuse": context(lines=(("WINE-RESERVE", "Wines"),)), "ask": context(grand=600000)}
        for want, ctx in cases.items():
            raw = body(ctx)
            code, out = self.post(raw, signed(raw))
            self.assertEqual((code, out["verdict"]), (200, want))

    def test_a_forged_check_is_refused(self):
        raw = body()
        code, out = self.post(raw, signed(raw, secret="not-the-shops-secret"))
        self.assertEqual((code, out["error"]), (401, "the signature does not match"))

    def test_a_body_changed_after_signing_is_refused(self):
        raw = body(context(lines=(("WINE-RESERVE", "Wines"),)))
        code, _ = self.post(body(context(lines=(("WINE-RESERVE", "Wines"),), group="Gold")), signed(raw))
        self.assertEqual(code, 401)

    def test_an_old_check_is_refused(self):
        raw = body()
        code, out = self.post(raw, signed(raw, ts=time.time() - 3600))
        self.assertEqual(code, 401)
        self.assertIn("time", out["error"])

    def test_a_body_it_cannot_read_is_a_400(self):
        for raw in (b"not json", json.dumps({"point": "check/1", "context": {"v": 1}}).encode()):
            code, _ = self.post(raw, signed(raw))
            self.assertEqual(code, 400)

    def test_only_its_own_path(self):
        raw = body()
        code, _ = self.post(raw, signed(raw), url=self.url.replace("/rgd/check", "/rgd/other"))
        self.assertEqual(code, 404)

    def test_the_service_answers_the_same_context_the_same_way(self):
        ctx = context(lines=(("WINE-RESERVE", "Wines"),))
        raw = body(copy.deepcopy(ctx))
        self.assertEqual(self.post(raw, signed(raw)), self.post(raw, signed(raw)))


if __name__ == "__main__":
    unittest.main()
