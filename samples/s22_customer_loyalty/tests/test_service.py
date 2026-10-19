"""S22's service against an in-memory shop: enrolment, earning, returns while Pending and after Credited, the cap,
cancellation, the crash between the shop's write and the handled-events note, tiers as groups, the member key over
signed presses, and check-by-workflow on the receipt. tests/canaries.py breaks each rule and expects a failure here."""

import base64
import hashlib
import hmac
import json
import os
import sys
import time
import unittest
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
sys.path[:0] = [HERE, os.path.join(SAMPLE, "service")]
import app  # noqa: E402
import loyalty  # noqa: E402
import receipts  # noqa: E402
import worker  # noqa: E402
import shop as shop_client  # noqa: E402
from fake_shop import sale, shop  # noqa: E402

F = worker.F
L = loyalty.LEDGER


def rows(t, **f):
    return [r for r in t.db.get(L, {}).values() if all(r.get(k) == v for k, v in f.items())]


class Earning(unittest.TestCase):
    def setUp(self):
        self.t = shop()
        self.s = loyalty.Settings.load(self.t)

    def test_enrol_once_into_the_default_group_never_the_walk_in(self):
        self.assertEqual(loyalty.enrol(self.t, self.s, "C1", "2026-10-01"), "enrolled")
        self.assertEqual(loyalty.enrol(self.t, self.s, "C1", "2026-10-01"), "already enrolled")
        self.assertEqual(self.t.db["Customer"]["C1"]["customer_group"], "PP LYL Bronze")
        self.assertEqual(loyalty.enrol(self.t, self.s, "Walk-in — Demo Retail", "2026-10-01"), "skipped")

    def test_a_sale_earns_pending_until_the_return_window_closes_then_credits(self):
        sale(self.t, "S1", "C1", "500.00")
        loyalty.on_sale(self.t, self.s, "S1", "2026-10-01")
        r = self.t.db[L]["POS Invoice:S1:earn"]
        self.assertEqual((r["status"], r["amount"], r["credit_on"]), ("Pending", Decimal("10.00"), "2026-10-16"))
        self.assertEqual(loyalty.credit_due(self.t, self.s, "2026-10-15"), [])
        self.assertEqual(loyalty.credit_due(self.t, self.s, "2026-10-16"), ["POS Invoice:S1:earn"])

    def test_a_sale_of_nothing_or_less_writes_no_earn_row(self):
        for name, total in (("S0", "0"), ("SN", "-5.00")):
            sale(self.t, name, "C1", total)
            self.assertEqual(loyalty.on_sale(self.t, self.s, name, "2026-10-01")["result"], "nothing to earn", name)
        self.assertEqual(rows(self.t), [])                              # no Earn row, and nothing else, for either


class EarningBase(unittest.TestCase):
    """What a sale earns on: what it sold, gift cards aside, less the goods' share of a tender discount; how it was paid
    does not matter (Member cash aside: test_wallet.Earning). Returns take back exactly what the sale earned, and the
    year's spend nets to 0. The lines carry what the engine writes: ``net_amount`` (after a sale discount) and the
    line's share of the tender discount (``custom_tender_discount_apportioned``)."""

    def setUp(self):
        self.t = shop()
        self.s = loyalty.Settings.load(self.t)

    def sell(self, name, total, items=(), payments=(), discount=0, taxes=(), conversion_rate=1, **kw):
        inv = sale(self.t, name, "C1", total, **kw)
        inv["conversion_rate"] = conversion_rate
        inv["items"] = [{"item_code": "GIFT" if ln[0].startswith("Gift") else "GOODS", "transaction_mode": ln[0],
                         "net_amount": ln[1], "amount": ln[3] if len(ln) > 3 else ln[1],
                         "custom_tender_discount_apportioned": ln[2] if len(ln) > 2 else 0} for ln in items]
        inv["payments"] = [{"type": k, "mode_of_payment": k, "amount": a} for k, a in payments]
        inv["custom_tender_discount_amount"] = discount
        inv["taxes"] = list(taxes)
        return loyalty.on_sale(self.t, self.s, name, kw.get("posting_date", "2026-10-01"))

    def back(self, name, total, against="S1", posting_date="2026-10-02", discount=0):
        return self.sell(name, total, [("Sale Return", total)], discount=discount, is_return=1, return_against=against,
                         posting_date=posting_date)

    def earn(self, name="S1"):
        r = self.t.db[L][f"POS Invoice:{name}:earn"]
        return Decimal(str(r["earned_amount"])), Decimal(str(r["sale_base"]))

    def nets_to_zero(self, sale_name="S1"):
        got = [r for r in rows(self.t) if r["against_sale"] == sale_name]
        earned = sum(Decimal(str(r["earned_amount"])) for r in got if r["entry_type"] == "Earn")
        taken = -sum(Decimal(str(r["amount"])) for r in got if r["entry_type"] != "Earn")
        self.assertEqual(taken, earned)
        self.assertEqual(loyalty.spend(self.t, self.s, "C1", "2026-10-20"), Decimal("0.00"))

    def test_a_gift_card_sold_on_the_sale_earns_nothing_on_it(self):
        self.sell("S1", "180.00", [("Sale", "100.00"), ("Gift Certificate", "50.00"), ("Gift Certificate Recharge", "30.00")])
        self.assertEqual(self.earn(), (Decimal("2.00"), Decimal("100.00")))
        self.assertEqual(self.sell("S2", "50.00", [("Gift Certificate", "50.00")])["result"], "nothing to earn")
        self.assertNotIn("POS Invoice:S2:earn", self.t.db[L])

    def test_a_gift_card_under_a_sale_discount_comes_off_at_what_it_added(self):
        # 10% off the sale: the goods 90 and the card 45 of a 135 grand total
        self.sell("S1", "135.00", [("Sale", "90.00", 0, "100.00"), ("Gift Certificate", "45.00", 0, "50.00")])
        self.assertEqual(self.earn(), (Decimal("1.80"), Decimal("90.00")))

    def test_a_taxed_gift_card_comes_off_with_its_tax_and_the_goods_return_takes_back_exactly(self):
        # the sandbox shop's 8% sales tax on every line, as the bench's till wrote it: 100 + 50 + 12 of tax = 162
        tax = [{"item_wise_tax_detail": '{"GOODS": [8.0, 8.0], "GIFT": [8.0, 4.0]}', "tax_amount": 12.0}]
        self.sell("S1", "162.00", [("Sale", "100.00"), ("Gift Certificate", "50.00")], taxes=tax)
        self.assertEqual(self.earn(), (Decimal("2.16"), Decimal("108.00")))
        self.back("R1", "-108.00")
        self.assertEqual(self.t.db[L]["POS Invoice:R1:return"]["amount"], Decimal("-2.16"))
        self.nets_to_zero()

    def test_a_taxed_gift_card_comes_off_whichever_shape_the_tax_rows_keep(self):
        tax = [{"item_wise_tax_detail": {"GOODS": {"tax_rate": 8, "tax_amount": 8}, "GIFT": {"tax_rate": 8, "tax_amount": 4}}}]
        self.sell("S1", "162.00", [("Sale", "100.00"), ("Gift Certificate", "50.00")], taxes=tax, conversion_rate="0")
        self.assertEqual(self.earn(), (Decimal("2.16"), Decimal("108.00")))

    def test_a_taxed_gift_card_in_another_currency_comes_off_at_the_sales_own_figure(self):
        # a sale in AED for a company in INR (rate 22.6): the tax rows keep each item's tax in the company's currency
        tax = [{"item_wise_tax_detail": '{"GOODS": [5.0, 113.0], "GIFT": [5.0, 56.5]}', "tax_amount": 7.5}]
        self.sell("S1", "157.50", [("Sale", "100.00"), ("Gift Certificate", "50.00")], taxes=tax, conversion_rate=22.6)
        self.assertEqual(self.earn(), (Decimal("2.10"), Decimal("105.00")))

    def test_a_gift_card_or_on_account_payment_still_earns_once(self):
        # the gift card earned nothing when it was sold, so it earns when it is spent; on account is the customer's own
        self.sell("S1", "100.00", [("Sale", "100.00")], [("Gift Certificate", "40.00"), ("On Account", "60.00")])
        self.assertEqual(self.earn(), (Decimal("2.00"), Decimal("100.00")))

    def test_the_tender_discount_is_left_out(self):
        self.sell("S1", "1000.00", [("Sale", "1000.00", "50.00")], [("Cash", "950.00")], discount="50.00")
        self.assertEqual(self.earn(), (Decimal("19.00"), Decimal("1000.00")))

    def test_a_mixed_sale_earns_on_the_rest_only_and_a_replay_writes_nothing(self):
        # a tender discount of 7.50 spread over the goods (5.00) and the card (2.50): the goods earn on 95
        out = self.sell("S1", "150.00", [("Sale", "100.00", "5.00"), ("Gift Certificate", "50.00", "2.50")],
                        [("Gift Certificate", "30.00"), ("On Account", "20.00"), ("Cash", "92.50")], discount="7.50")
        self.assertEqual(self.earn(), (Decimal("1.90"), Decimal("100.00")))
        self.assertTrue(out["row_made"])
        self.assertFalse(loyalty.on_sale(self.t, self.s, "S1", "2026-10-01")["row_made"])
        self.assertEqual(len(rows(self.t)), 1)

    def test_returning_the_goods_of_a_gift_card_sale_takes_back_exactly_what_was_earned(self):
        # 100 of goods and a gift card of 50 earns 2.00; the goods' return takes 2.00 (by the grand total it took 1.33)
        self.sell("S1", "150.00", [("Sale", "100.00"), ("Gift Certificate", "50.00")])
        self.back("R1", "-100.00")
        self.assertEqual(self.t.db[L]["POS Invoice:R1:return"]["amount"], Decimal("-2.00"))
        self.nets_to_zero()

    def test_returns_after_a_tender_discount_take_back_exactly_what_was_earned(self):
        self.sell("S1", "1000.00", [("Sale", "1000.00", "50.00")], discount="50.00")       # earns 19.00 on 950
        for name in ("R1", "R2"):                                   # each half carries back its half of the discount
            self.back(name, "-500.00", discount="-25.00")
        self.assertEqual(self.t.db[L]["POS Invoice:R1:return"]["amount"], Decimal("-9.50"))
        self.nets_to_zero()

    def test_returns_in_parts_take_back_exactly_what_was_earned_whatever_the_tender_discounts_rounding(self):
        # three lines of 10.00 and a tender discount of 1.01: the engine rounds each return's share (0.34) on its own
        self.sell("S1", "30.00", [("Sale", "10.00", "0.34"), ("Sale", "10.00", "0.34"), ("Sale", "10.00", "0.33")],
                  discount="1.01")
        self.assertEqual(self.earn(), (Decimal("0.58"), Decimal("30.00")))                  # 2% of 28.99
        for name in ("R1", "R2", "R3"):
            self.back(name, "-10.00", discount="-0.34")
        self.nets_to_zero()

    def test_a_mixed_sale_returned_after_its_credit_nets_to_zero(self):
        self.sell("S1", "150.00", [("Sale", "100.00", "5.00"), ("Gift Certificate", "50.00", "2.50")],
                  [("Gift Certificate", "30.00"), ("On Account", "20.00"), ("Cash", "92.50")], discount="7.50")
        loyalty.credit_due(self.t, self.s, "2026-10-16")
        self.back("R1", "-100.00", posting_date="2026-10-17", discount="-5.00")     # the goods' share, as the engine writes
        self.assertEqual(loyalty.balance(self.t, "C1"), (Decimal("0.00"), Decimal("0")))
        self.nets_to_zero()

    def test_a_row_written_before_the_rule_changed_is_still_taken_back_whole(self):
        # an earning written by 1.0.0 kept the whole grand total (1000, a tender discount of 50 inside it)
        self.t.insert({"doctype": L, "source_key": "POS Invoice:S1:earn", "customer": "C1", "entry_type": "Earn",
                       "status": "Pending", "amount": Decimal("20.00"), "earned_amount": Decimal("20.00"),
                       "sale_base": Decimal("1000"), "against_sale": "S1", "posting_date": "2026-10-01",
                       "credit_on": "2026-10-16"})
        self.back("R1", "-1000.00", discount="-50.00")
        self.nets_to_zero()


class Balances(unittest.TestCase):
    """The balance report recipe: one row per member per day, opening = the last closing, idempotent."""

    def setUp(self):
        self.t = shop()
        self.s = loyalty.Settings.load(self.t)
        loyalty.enrol(self.t, self.s, "C1", "2026-10-01")
        sale(self.t, "S1", "C1", "500.00")
        loyalty.on_sale(self.t, self.s, "S1", "2026-10-01")

    def bal(self, d):
        return self.t.db[loyalty.BALANCE][f"balance:C1:{d}"]

    def test_a_day_opens_at_the_last_close_and_a_second_run_writes_nothing(self):
        self.assertEqual(loyalty.daily_balances(self.t, self.s, "2026-10-16"), ["balance:C1:2026-10-15"])
        self.assertEqual((self.bal("2026-10-15")["opening"], self.bal("2026-10-15")["closing"]), (Decimal("0.00"), Decimal("0.00")))
        loyalty.credit_due(self.t, self.s, "2026-10-16")                         # the earning becomes spendable
        self.assertEqual(loyalty.daily_balances(self.t, self.s, "2026-10-17"), ["balance:C1:2026-10-16"])
        d = self.bal("2026-10-16")
        self.assertEqual((d["opening"], d["change"], d["closing"]), (Decimal("0.00"), Decimal("10.00"), Decimal("10.00")))
        self.assertEqual(loyalty.daily_balances(self.t, self.s, "2026-10-17"), [], "a second run of the day wrote again")
        self.assertEqual(loyalty.daily_balances(self.t, self.s, "2026-10-18")[0], "balance:C1:2026-10-17")
        self.assertEqual(self.bal("2026-10-17")["opening"], Decimal("10.00"))

    def test_pending_cash_back_is_not_in_the_balance(self):
        loyalty.daily_balances(self.t, self.s, "2026-10-02")
        self.assertEqual(self.bal("2026-10-01")["closing"], Decimal("0.00"))


class TakingBack(unittest.TestCase):
    def setUp(self):
        self.t = shop()
        self.s = loyalty.Settings.load(self.t)
        sale(self.t, "S1", "C1", "1000.00")
        loyalty.on_sale(self.t, self.s, "S1", "2026-10-01")

    def ret(self, name, value):
        sale(self.t, name, "C1", f"-{value}", is_return=1, return_against="S1", posting_date="2026-10-02")
        return loyalty.on_sale(self.t, self.s, name, "2026-10-02")

    def test_a_partial_return_while_pending_reduces_the_earning(self):
        self.assertEqual(self.ret("R1", "333.33")["amount"], "6.67")
        earn = self.t.db[L]["POS Invoice:S1:earn"]
        self.assertEqual((earn["status"], earn["amount"]), ("Pending", Decimal("13.33")))

    def test_the_credit_settles_an_unsettled_return_first(self):
        # a return's row written but its settle lost (a crash, an error): the daily credit nets it first
        self.t.insert({"doctype": L, "source_key": "POS Invoice:R9:return", "customer": "C1", "entry_type": "Return",
                       "status": "Netted", "amount": Decimal("-5.00"), "sale_base": Decimal("-250"), "against_sale": "S1"})
        loyalty.credit_due(self.t, self.s, "2026-10-30")
        earn = self.t.db[L]["POS Invoice:S1:earn"]
        self.assertEqual((earn["status"], Decimal(str(earn["amount"]))), ("Credited", Decimal("15.00")))

    def test_a_return_after_credit_is_a_negative_row(self):
        loyalty.credit_due(self.t, self.s, "2026-10-16")
        self.ret("R1", "500.00")
        self.assertEqual(self.t.db[L]["POS Invoice:R1:return"]["amount"], Decimal("-10.00"))
        self.assertEqual(loyalty.balance(self.t, "C1"), (Decimal("10.00"), Decimal("0")))

    def test_returns_never_take_back_more_than_was_earned(self):
        for i, v in enumerate(("333.33", "333.33", "333.34", "50.00")):
            self.ret(f"R{i}", v)
        self.assertEqual(-sum(r["amount"] for r in rows(self.t, entry_type="Return")), Decimal("20.00"))

    def test_a_cancelled_sale_takes_back_the_rest(self):
        loyalty.credit_due(self.t, self.s, "2026-10-16")
        self.ret("R1", "250.00")
        self.assertEqual(loyalty.on_cancel(self.t, self.s, "S1", "2026-10-20")["amount"], "15.00")
        self.assertEqual(loyalty.balance(self.t, "C1")[0], Decimal("0.00"))

    def test_cancelling_the_sale_after_a_return_takes_the_returned_part_out_of_the_spend_once(self):
        self.ret("R1", "250.00")
        self.assertEqual(loyalty.spend(self.t, self.s, "C1", "2026-10-20"), Decimal("750.00"))
        loyalty.on_cancel(self.t, self.s, "S1", "2026-10-20")
        self.assertEqual(loyalty.spend(self.t, self.s, "C1", "2026-10-21"), Decimal("0.00"))      # not -250
        loyalty.on_cancel(self.t, self.s, "S1", "2026-10-20")                                    # the replay: same row
        self.assertEqual(loyalty.spend(self.t, self.s, "C1", "2026-10-21"), Decimal("0.00"))

    def test_a_return_that_was_cancelled_first_still_leaves_the_sale_cancelled_at_zero_spend(self):
        self.ret("R1", "250.00")
        self.assertEqual(loyalty.on_cancel(self.t, self.s, "R1", "2026-10-19")["result"], "the sale earned nothing")
        self.assertEqual(len(rows(self.t, entry_type="Return")), 1)                  # the Return row is not removed
        loyalty.on_cancel(self.t, self.s, "S1", "2026-10-20")
        self.assertEqual(loyalty.spend(self.t, self.s, "C1", "2026-10-21"), Decimal("0.00"))
        self.assertEqual(loyalty.balance(self.t, "C1"), (Decimal("0.00"), Decimal("0.00")))   # and the money is right


class Crash(unittest.TestCase):
    """Killed after the shop wrote the row and before the handled-events note: the event comes back, the shop refuses
    the second row by its unique key, still one row."""

    class Feed:
        def __init__(self, events):
            self.q = list(events)

        def events(self, limit=100, page=None):
            return list(self.q), None, len(self.q)

        def done(self, ids):
            self.q = [e for e in self.q if e["id"] not in ids]
            return len(ids)

        def failed(self, id_, note):
            raise AssertionError(note)

        def backlog(self):
            return len(self.q)

    def test_the_replay_after_a_crash_writes_one_row(self):
        t = shop()
        sale(t, "S1", "C1", 1000)
        feed = self.Feed([{"id": "e1", "event": "sale.booked", "doc_type": "POS Invoice", "doc_name": "S1"}])
        store = F.Store(":memory:")
        t.fail_after_insert = L
        with self.assertRaises(SystemExit):
            F.poll(feed, store, worker.handle(t, "2026-10-01"))
        self.assertFalse(store.seen("e1"))
        F.poll(feed, store, worker.handle(t, "2026-10-01"))
        self.assertEqual(len(rows(t, against_sale="S1")), 1)
        self.assertEqual(feed.backlog(), 0)

    def test_the_door_is_asked_with_post(self):
        class Api:
            def call(self, method, path, params=None, body=None):
                self.seen = (method, path, body)
                return {"message": {"events": [], "page": None, "backlog": 0}}
        api = Api()
        F.DoorFeed(api).events(limit=5)
        self.assertEqual(api.seen, ("POST", "/api/method/ivendnext_mpos.api.feed.events", {"limit": 5}))


class ShopClient(unittest.TestCase):
    def test_every_call_to_the_shop_names_the_service_not_the_librarys_default(self):
        seen = []

        class Reply:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self):
                return b'{"data": {"name": "C1"}}'

        class Opener:
            def open(self, req, timeout=None):
                seen.append(req)
                return Reply()

        c = shop_client.Shop("https://shop.example", "key", "secret")
        c._opener = Opener()
        c.get("Customer", "C1")
        c.list("Customer")
        c.insert({"doctype": "Customer", "customer_name": "C1"})
        c.update("Customer", "C1", {"mobile_no": "1"})
        c.method("ping")
        self.assertEqual(len(seen), 5)
        for req in seen:
            self.assertEqual(req.get_header("User-agent"), shop_client.USER_AGENT)
            self.assertNotIn("urllib", req.get_header("User-agent").lower())


class Tiers(unittest.TestCase):
    def test_spend_moves_the_member_by_moving_the_group(self):
        t = shop()
        s = loyalty.Settings.load(t)
        sale(t, "S1", "C1", "1200.00")
        loyalty.on_sale(t, s, "S1", "2026-10-01")
        self.assertEqual(loyalty.evaluate_tiers(t, s, "2026-10-02"), [{"customer": "C1", "from": "Bronze", "to": "Silver"}])
        self.assertEqual(t.db["Customer"]["C1"]["customer_group"], "PP LYL Silver")
        sale(t, "R1", "C1", "-1200.00", is_return=1, return_against="S1")
        loyalty.on_sale(t, s, "R1", "2026-10-03")
        loyalty.evaluate_tiers(t, s, "2026-10-04")
        self.assertEqual(t.db["Customer"]["C1"]["customer_group"], "PP LYL Bronze")

    def test_a_customer_the_shop_refuses_to_save_does_not_stop_the_others(self):
        t = shop()
        t.put("Customer", "C2", customer_group="Individual")
        s = loyalty.Settings.load(t)
        for name, cust in (("S1", "C1"), ("S2", "C2")):
            sale(t, name, cust, "1200.00")
            loyalty.on_sale(t, s, name, "2026-10-01")
        real = t.update

        def update(dt, name, fields):
            if dt == "Customer" and name == "C1":
                raise loyalty.ShopError(417, "a mandatory field the shop added")
            return real(dt, name, fields)

        t.update = update
        moved = loyalty.evaluate_tiers(t, s, "2026-10-02")
        self.assertIn({"customer": "C1", "refused": 417}, moved)                    # counted, not raised
        self.assertEqual(t.db["PP LYL Member"]["C1"]["plan"], "Bronze")             # its plan waits for its group
        self.assertEqual(t.db["Customer"]["C2"]["customer_group"], "PP LYL Silver")  # the next member still moved
        self.assertEqual(len(loyalty.daily_balances(t, s, "2026-10-02")), 2)          # and the balances still run


class MemberKey(unittest.TestCase):
    SECRET = "m" * 32

    def press(self, svc, body, secret=None, ts=None):
        raw = json.dumps(body).encode()
        ts = str(int(ts or time.time()))
        sig = base64.b64encode(hmac.new((secret or self.SECRET).encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
        return svc.press({"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig.decode()}, raw)

    def test_the_key_shows_plan_balance_and_next_tier_and_refuses_a_bad_signature(self):
        t = shop()
        s = loyalty.Settings.load(t)
        sale(t, "S1", "C1", "400.00")
        loyalty.on_sale(t, s, "S1", "2026-10-01")
        svc = app.Service({"PP_KEY_SECRET": self.SECRET}, shop=t)
        code, ans = self.press(svc, {"app": "pp_lyl", "key": "pp_lyl_member", "context": {"customer": "C1", "lines": []}})
        self.assertEqual(code, 200)
        self.assertEqual(ans["message"]["title"], "Bronze member")
        self.assertIn("USD 8.00 pending", ans["message"]["body"])
        self.assertIn("more reaches Silver (spend over the last 365 days).", ans["message"]["body"])
        t.db["PP LYL Settings"]["Default"]["tier_window_days"] = 90                # the shop's own window, in its words
        self.assertIn("(spend over the last 90 days).", self.press(svc, {"context": {"customer": "C1"}})[1]["message"]["body"])
        t.db["PP LYL Member"]["C1"]["status"] = "Inactive"                          # no move promised to an inactive member
        body = self.press(svc, {"context": {"customer": "C1"}})[1]["message"]["body"]
        self.assertIn("Plan moves are stopped", body)
        self.assertNotIn("reaches Silver", body)
        self.assertEqual(self.press(svc, {"context": {}}, secret="x" * 32)[0], 401)
        self.assertEqual(self.press(svc, {"context": {}}, ts=time.time() - 3600)[0], 401)


class CheckByWorkflow(unittest.TestCase):
    def setUp(self):
        self.t = shop()
        self.t.put("Purchase Order", "PO1", items=[{"name": "poi1", "qty": 10, "received_qty": 6}])
        self.t.put("Purchase Receipt", "PR1", docstatus=0, workflow_state=receipts.PENDING,
                   items=[{"idx": 1, "item_code": "A", "qty": 5, "purchase_order": "PO1", "purchase_order_item": "poi1"}])

    def test_verified_only_when_the_check_passes_and_only_once(self):
        self.assertEqual(receipts.on_receipt(self.t, "PR1")["result"], "not verified")       # 5 received, 4 awaited
        self.assertEqual(self.t.db["Purchase Receipt"]["PR1"]["workflow_state"], receipts.PENDING)
        self.assertEqual(len(self.t.db["Comment"]), 1)
        self.t.db["Purchase Receipt"]["PR1"]["items"][0]["qty"] = 4
        self.assertEqual(receipts.on_receipt(self.t, "PR1")["result"], "verified")
        self.assertEqual(receipts.on_receipt(self.t, "PR1")["result"], "not waiting for verification")
        self.assertEqual(self.t.calls.count(("method", "ivendnext_mpos.api.v1.apply_workflow")), 1)


if __name__ == "__main__":
    unittest.main()
