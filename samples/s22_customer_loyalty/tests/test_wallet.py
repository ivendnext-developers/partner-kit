"""S22's Member cash (service/wallet.py) against an in-memory shop: the preview and its cap, one charge per reference,
the balance, status about the asked reference, reversal, refunds in parts, the earning on a sale paid with Member cash,
and the signed route.

Adapted from CitiXsys's private reference implementation's wallet tests @ 74c99d5 (its expiry tests left out: S22 keeps
no expiry); a defect here may be a defect there — report it on the Partner feedback forms."""

import base64
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "service"))
import app  # noqa: E402
import loyalty  # noqa: E402
import wallet  # noqa: E402
from fake_shop import sale, shop  # noqa: E402
from shop import ShopError  # noqa: E402

L = loyalty.LEDGER
loyalty.LOCKS = tempfile.mkdtemp(prefix="s22-locks-")
wallet.STARTED = time.monotonic() - wallet.SETTLE_S - 1          # the tests run long after a start, unless one says not
SITE, MERCHANT, SECRET = "site-1", "STORE-1", "w" * 32


def credited(t, customer="C1", amount="100.00", name="E1"):
    t.insert({"doctype": L, "source_key": f"POS Invoice:{name}:earn", "customer": customer, "entry_type": "Earn",
              "status": "Credited", "amount": Decimal(amount), "earned_amount": Decimal(amount),
              "sale_base": Decimal(amount) * 50, "against_sale": name, "posting_date": "2026-09-01"})


def member_shop(percent=50):
    t = shop()
    t.db["PP LYL Settings"]["Default"].update(max_redemption_percent=percent, wallet_mode_of_payment="Member cash",
                                              earn_on_redemption=0)
    t.put("PP LYL Member", "C1", customer="C1", plan="Bronze", status="Active")
    credited(t)
    return t


def req(verb, **kw):
    base = {"v": 1, "verb": verb, "site": SITE, "merchant": MERCHANT, "currency": "USD", "currency_exponent": 2}
    return dict(base, **kw)


def ask(ref, **kw):
    """The shop's own status question: no currency, no exponent, no merchant (ivendnext_pay_remote adapter.get_status)."""
    return dict({"v": 1, "verb": "status", "site": SITE, "reference": ref}, **kw)


def pay(ref, minor, party="C1"):
    return req("authorise", reference=ref, amount_minor=minor, rail="wallet", payer={"party": party})


class Wallet(unittest.TestCase):
    def setUp(self):
        wallet._declined.clear()
        self.t = member_shop()
        self.s = loyalty.Settings.load(self.t)
        self.w = wallet.Wallet(self.t, {"PP_WALLET_MERCHANT": MERCHANT})

    def call(self, body):
        code, out = self.w.answer(body["verb"], body, self.s)
        self.assertEqual(code, 200, out)
        return out

    def bal(self):
        return loyalty.balance(self.t, "C1")[0]

    def test_preview_caps_at_the_percent_of_the_amount_due_and_the_balance(self):
        before = len(self.t.calls)
        out = self.call(req("preview", customer="C1", amount_due_minor=15000))
        self.assertEqual((out["eligible"], out["balance_minor"], out["max_redeemable_minor"], out["label"]),
                         (True, 10000, 7500, "Member cash"))
        out = self.call(req("preview", customer="C1", amount_due_minor=50000))
        self.assertEqual(out["max_redeemable_minor"], 10000)                       # the balance, not 50 % of 500
        self.assertEqual([c for c in self.t.calls[before:] if c[0] != "docinfo"], [])     # a preview writes nothing

    def test_preview_refuses_a_non_member_a_foreign_merchant_and_another_currency(self):
        for body in (req("preview", customer="C9", amount_due_minor=100),
                     req("preview", customer="C1", amount_due_minor=100, merchant="SOMEONE"),
                     req("preview", customer="C1", amount_due_minor=100, currency="EUR")):
            out = self.call(body)
            self.assertEqual((out["eligible"], bool(out.get("reason"))), (False, True), body)

    def test_no_limit_when_the_percent_is_zero(self):
        self.t.db["PP LYL Settings"]["Default"]["max_redemption_percent"] = 0
        self.s = loyalty.Settings.load(self.t)
        out = self.call(req("preview", customer="C1", amount_due_minor=6000))
        self.assertEqual(out["max_redeemable_minor"], 6000)

    def test_authorise_twice_with_one_reference_is_one_charge(self):
        a = self.call(pay("MPOS-REF-1", 4000))
        b = self.call(pay("MPOS-REF-1", 4000))
        self.assertEqual((a["outcome"], a["amount_minor"], a["auth_ref"]), ("approved", 4000, b["auth_ref"]))
        self.assertEqual(len([r for r in self.t.db[L].values() if r["entry_type"] == "Redeem"]), 1)
        self.assertEqual(self.bal(), Decimal("60.00"))

    def test_more_than_the_balance_is_refused_and_stays_refused(self):
        a = self.call(pay("MPOS-REF-2", 10001))
        self.assertEqual((a["outcome"], a["reason"]), ("declined", "insufficient_funds"))
        self.assertEqual(self.bal(), Decimal("100.00"))
        credited(self.t, amount="50.00", name="E2")                               # more cash back arrives meanwhile
        self.assertEqual(self.call(pay("MPOS-REF-2", 10001))["outcome"], "declined")

    def test_status_answers_the_asked_reference_and_proves_absence(self):
        self.call(pay("MPOS-REF-3", 1000))
        self.call(pay("MPOS-REF-4", 2000))
        out = self.call(ask("MPOS-REF-3"))
        self.assertEqual((out["reference"], out["outcome"], out["amount_minor"], out["currency"]),
                         ("MPOS-REF-3", "approved", 1000, "USD"))
        out = self.call(ask("MPOS-REF-NEVER"))
        self.assertEqual((out["outcome"], out["exists"]), ("unknown", False))

    def test_reverse_gives_the_whole_payment_back_once(self):
        a = self.call(pay("MPOS-REF-5", 3000))
        for _ in range(2):
            out = self.call(req("reverse", reference="MPOS-REF-5", auth_ref=a["auth_ref"], amount_minor=3000))
            self.assertEqual((out["outcome"], out["amount_minor"]), ("approved", 3000))
        self.assertEqual(self.bal(), Decimal("100.00"))
        self.assertEqual(self.call(ask("MPOS-REF-5"))["outcome"], "declined")

    def test_reverse_of_a_reference_never_received(self):
        out = self.call(req("reverse", reference="MPOS-REF-X", amount_minor=500))
        self.assertEqual((out["outcome"], out["amount_minor"]), ("approved", 0))
        out = self.call(req("reverse", reference="MPOS-REF-Y", auth_ref="PPA-1", amount_minor=500))
        self.assertEqual(out["outcome"], "unknown")

    def test_a_payment_refunded_in_two_parts_each_answered_for_itself_and_never_more(self):
        a = self.call(pay("MPOS-REF-6", 5000))
        r1 = self.call(req("refund", reference="MPOS-RFD-1", original_reference="MPOS-REF-6", auth_ref=a["auth_ref"],
                           amount_minor=2000))
        r1b = self.call(req("refund", reference="MPOS-RFD-1", original_reference="MPOS-REF-6", auth_ref=a["auth_ref"],
                            amount_minor=2000))
        r2 = self.call(req("refund", reference="MPOS-RFD-2", original_reference="MPOS-REF-6", auth_ref=a["auth_ref"],
                           amount_minor=3000))
        r3 = self.call(req("refund", reference="MPOS-RFD-3", original_reference="MPOS-REF-6", auth_ref=a["auth_ref"],
                           amount_minor=1))
        self.assertEqual((r1["outcome"], r1["amount_minor"], r1["reference"]), ("approved", 2000, "MPOS-RFD-1"))
        self.assertEqual(r1b["correlation_id"], r1["correlation_id"])
        self.assertNotEqual(r2["correlation_id"], r1["correlation_id"])
        self.assertEqual((r2["amount_minor"], r3["outcome"]), (3000, "declined"))
        self.assertEqual(self.bal(), Decimal("100.00"))
        out = self.call(ask("MPOS-RFD-2", correlation_id=r2["correlation_id"]))
        self.assertEqual((out["outcome"], out["amount_minor"], out["correlation_id"]),
                         ("approved", 3000, r2["correlation_id"]))

    def test_a_refund_of_a_reversed_payment_is_refused(self):
        a = self.call(pay("MPOS-REF-7", 1000))
        self.call(req("reverse", reference="MPOS-REF-7", auth_ref=a["auth_ref"], amount_minor=1000))
        out = self.call(req("refund", reference="MPOS-RFD-9", original_reference="MPOS-REF-7", auth_ref=a["auth_ref"],
                            amount_minor=1000))
        self.assertEqual(out["outcome"], "declined")
        self.assertEqual(self.bal(), Decimal("100.00"))

    def test_a_write_that_may_still_land_is_never_absent(self):
        def fail(doc):
            raise ShopError(0, "timed out")
        self.t.insert = fail
        with self.assertRaises(ShopError):
            self.call(pay("MPOS-REF-U", 1000))
        out = self.call(ask("MPOS-REF-U"))
        self.assertEqual((out["outcome"], "exists" in out), ("unknown", False))

    def test_a_reversal_that_may_still_land_keeps_status_unknown(self):
        self.call(pay("MPOS-REF-V", 1000))

        def fail(doc):
            raise ShopError(0, "timed out")
        self.t.insert = fail
        with self.assertRaises(ShopError):
            self.call(req("reverse", reference="MPOS-REF-V", auth_ref="x"))
        self.assertEqual(self.call(ask("MPOS-REF-V"))["outcome"], "unknown")       # never "approved, captured"

    def test_just_after_a_start_status_never_says_not_here(self):
        self.call(pay("MPOS-REF-S", 1000))
        self.call(req("reverse", reference="MPOS-REF-S", auth_ref="x"))
        wallet.STARTED = time.monotonic()
        try:
            out = self.call(ask("MPOS-REF-NEVER"))
            self.assertEqual((out["outcome"], "exists" in out), ("unknown", False))
            self.assertEqual(self.call(ask("MPOS-REF-S"))["outcome"], "declined")  # a reversal row settles it
        finally:
            wallet.STARTED = time.monotonic() - wallet.SETTLE_S - 1

    def test_an_authorise_past_its_deadline_writes_nothing(self):
        clock = iter([0, wallet.WRITE_DEADLINE_S + 1])
        real = wallet.time.monotonic
        wallet.time.monotonic = lambda: next(clock)
        try:
            with self.assertRaises(TimeoutError):
                self.w.answer("authorise", pay("MPOS-REF-D", 1000), self.s)
        finally:
            wallet.time.monotonic = real
        self.assertIsNone(self.t.db[L].get(wallet._key(SITE, "MPOS-REF-D")))

    def test_a_money_call_without_its_exponent_is_refused(self):
        body = pay("MPOS-REF-X", 1000)
        del body["currency_exponent"]
        self.assertEqual(self.w.answer("authorise", body, self.s)[0], 422)
        self.assertEqual(self.w.answer("authorise", dict(body, currency_exponent=None), self.s)[0], 422)

    def test_a_refund_that_waited_for_the_lock_sees_the_reversal(self):
        self.call(pay("MPOS-REF-L", 4000))
        got = {}
        with loyalty.member_lock("C1"):
            th = threading.Thread(target=lambda: got.update(out=self.call(
                req("refund", reference="RF-L", original_reference="MPOS-REF-L", amount_minor=1000))))
            th.start()
            time.sleep(0.2)
            self.assertTrue(th.is_alive())                                          # waiting for the member's lock
            self.t.insert({"doctype": L, "source_key": wallet._key(SITE, "MPOS-REF-L", "reverse"), "customer": "C1",
                           "entry_type": "Redeem reversal", "status": "Credited", "amount": Decimal("40.00"),
                           "sale_base": 0, "against_sale": "MPOS-REF-L", "posting_date": "2026-10-12"})
        th.join(5)
        self.assertEqual(got["out"]["outcome"], "declined")
        self.assertEqual(self.bal(), Decimal("100.00"))                            # given back once, not twice

    def test_another_shops_question_says_nothing_about_money(self):
        w = wallet.Wallet(self.t, {"PP_WALLET_MERCHANT": MERCHANT, "PP_WALLET_SITE": "site-2"})
        for verb, body in (("status", ask("R1")), ("reverse", req("reverse", reference="R1", amount_minor=1))):
            out = w.answer(verb, body, self.s)[1]
            self.assertEqual((out["outcome"], out["reason"]), ("unknown", "config_invalid"), verb)

    def test_the_declaration_asks_nothing_of_the_customers_phone(self):
        # Member cash needs no mobile number: the till's wallet sheet must not ask for one (payer_required false)
        out = self.call(req("declaration"))
        self.assertIs(out["payer_required"], False)
        self.assertIs(wallet.DECLARATION["payer_required"], False)
        self.assertEqual(out["rails"], {"wallet": {"settlement": "synchronous", "can_prove_absence": True}})

    def test_the_verb_must_be_the_route_and_test_verbs_are_refused(self):
        self.assertEqual(self.w.answer("status", req("authorise", reference="R"), self.s)[0], 422)
        self.assertEqual(self.w.answer("induce", req("induce", condition="decline"), None)[0], 403)


class Earning(unittest.TestCase):
    def test_a_sale_paid_with_member_cash_earns_nothing_unless_the_shop_says_so(self):
        for earn_on, want, status in ((0, Decimal("0.00"), "Cancelled"), (1, Decimal("20.00"), "Pending")):
            t = member_shop()
            t.db["PP LYL Settings"]["Default"]["earn_on_redemption"] = earn_on
            s = loyalty.Settings.load(t)
            inv = sale(t, "S1", "C1", "1000.00")
            inv["payments"] = [{"mode_of_payment": "Member cash", "amount": 100}, {"mode_of_payment": "Cash", "amount": 900}]
            loyalty.on_sale(t, s, "S1", "2026-10-01")
            row = t.db[L]["POS Invoice:S1:earn"]
            self.assertEqual((Decimal(str(row["amount"])), row["status"]), (want, status), earn_on)
            self.assertEqual(loyalty.balance(t, "C1")[1], want, earn_on)        # a Cancelled row is never pending

    def test_a_sale_paid_with_member_cash_still_counts_towards_the_tier(self):
        # found by review: with no Earn row the sale fell out of the year's spend, and the daily job moved the member down
        t = member_shop()
        s = loyalty.Settings.load(t)
        inv = sale(t, "S2", "C1", "2000.00", posting_date="2026-10-01")
        inv["payments"] = [{"mode_of_payment": "Member cash", "amount": 0.01}, {"mode_of_payment": "Cash", "amount": 1999.99}]
        loyalty.on_sale(t, s, "S2", "2026-10-01")
        self.assertEqual(loyalty.spend(t, s, "C1", "2026-10-02"), Decimal("7000.00"))   # E1's 5,000 and this 2,000
        sale(t, "R2", "C1", "-2000.00", posting_date="2026-10-02", is_return=1, return_against="S2")
        loyalty.on_sale(t, s, "R2", "2026-10-02")                                      # the return still finds the row
        self.assertEqual(loyalty.spend(t, s, "C1", "2026-10-03"), Decimal("5000.00"))
        self.assertEqual(loyalty.balance(t, "C1")[0], Decimal("100.00"))               # and moves no money


def signed(body, secret=SECRET):
    raw = json.dumps(body).encode()
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw


class Route(unittest.TestCase):
    def test_the_route_is_signed_and_off_until_the_secret_is_set(self):
        wallet._declined.clear()
        t = member_shop()
        state = tempfile.mkdtemp(prefix="s22-state-")
        on = app.Service({"PP_KEY_SECRET": "k", "PP_WALLET_SECRET": SECRET, "PP_WALLET_MERCHANT": MERCHANT,
                          "PP_STATE": state}, shop=t)
        off = app.Service({"PP_KEY_SECRET": "k", "PP_WALLET_SECRET": "UNSET", "PP_STATE": state}, shop=t)
        h, raw = signed(pay("MPOS-REF-R", 100))
        self.assertEqual(off.wallet_answer("authorise", h, raw)[0], 404)
        self.assertEqual(on.wallet_answer("authorise", {}, raw)[0], 401)
        code, out = on.wallet_answer("authorise", h, raw)
        self.assertEqual((code, out["outcome"]), (200, "approved"))

    def test_the_web_handler_sends_the_wallet_path_to_the_wallet(self):
        from http.server import ThreadingHTTPServer
        import urllib.error
        import urllib.request
        wallet._declined.clear()
        svc = app.Service({"PP_KEY_SECRET": "k", "PP_WALLET_SECRET": SECRET, "PP_WALLET_MERCHANT": MERCHANT,
                           "PP_STATE": tempfile.mkdtemp(prefix="s22-state-")}, shop=member_shop())
        srv = ThreadingHTTPServer(("127.0.0.1", 0), app.make_handler(svc))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            h, raw = signed({"v": 1, "verb": "declaration"})
            r = urllib.request.Request(f"http://127.0.0.1:{srv.server_port}/paygw/1/declaration", data=raw, headers=h)
            with urllib.request.urlopen(r, timeout=5) as resp:
                self.assertEqual(json.loads(resp.read())["display_name"], "Member cash")
            with self.assertRaises(urllib.error.HTTPError) as e:                       # unsigned: refused
                urllib.request.urlopen(urllib.request.Request(r.full_url, data=raw), timeout=5)
            self.assertEqual(e.exception.code, 401)
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
