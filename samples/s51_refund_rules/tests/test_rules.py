"""S51's rules (``refunds.on_check``, ``refunds.settings_of``, ``refunds.check_context``): a
refund against a sale goes back by the methods that paid it, its store credit and the always-allowed ones; a return without its
sale by the methods named and its store credit; a sale, a return whose money goes nowhere and no settings are never judged; and every sentence is plain text the till accepts.

    python3 -m unittest discover -s samples/s51_refund_rules/tests -p 'test_*.py'
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE)]
import refunds  # noqa: E402

CASH, CARD, CREDIT, ONLINE, VOUCHER = "Cash", "Credit Card", "Store Credit", "Online Refund", "Gift Voucher"
OFFERED = [CASH, CARD, CREDIT, ONLINE]


def rows(*methods):
    return [{"name": f"r{i}", "parentfield": "x", "mode_of_payment": m} for i, m in enumerate(methods)]


# the retailer's record as the record API returns it: the header and its two tables
DOC = {"name": "Default", "title": "Default", "same_methods": 1, "store_credit": CREDIT, "always_allowed": [],
       "without_sale": rows(CREDIT)}


def settings(**kw):
    return refunds.settings_of(dict(DOC, **kw))


def line(n=1, qty=-1, rate=4990):
    return {"line_no": n, "item_code": "CASE", "item_group": "Accessories", "qty_milli": round(qty * 1000), "uom": "Nos",
            "rate_minor": rate, "amount_minor": round(rate * qty), "discount_minor": 0, "line_attributes": []}


def context(stage="return", channel="pos", paid_by=(CARD,), invoice="ACC-PSINV-1", offered=None, store="Main - S",
            lines=None, grand=None):
    lines = lines if lines is not None else [line()]
    total = sum(x["amount_minor"] for x in lines) if grand is None else grand
    ctx = {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "r-1", "store": store,
           "pos_profile": "Main Counter", "company": "Retailer", "currency": "AED", "lang": "en",
           "operator": "c@retailer.example", "customer": "CUST-1", "customer_group": "Retail",
           "price_list": "Standard Selling", "coupon_codes": [], "sale_attributes": [], "lines": lines,
           "totals": {"net_minor": total, "tax_minor": 0, "discount_minor": 0, "grand_minor": total},
           "offered_tenders": list(OFFERED if offered is None else offered), "pos_opening": "POS-OPE-1",
           "pos_terminal": "Main Counter 2"}
    if stage == "return":
        ctx["return_of"] = {"invoice": "" if channel == "none" else invoice, "channel": channel,
                            "paid_by": [] if channel == "none" else list(paid_by)}
    return ctx


def check(ctx=None, s=None):
    return refunds.on_check(ctx or context(), settings() if s is None else s)


class SameMethods(unittest.TestCase):
    def test_a_card_sale_is_refunded_by_card_or_store_credit_only(self):
        self.assertEqual(check(), {"verdict": "allow", "exclude_tenders": [CASH, ONLINE],
                                   "reason": "Refunded only by the methods that paid the sale."})

    def test_every_method_that_paid_the_sale_stays(self):
        out = check(context(paid_by=(CASH, CARD)))
        self.assertEqual(out["exclude_tenders"], [ONLINE])

    def test_the_always_allowed_methods_stay(self):
        out = check(s=settings(always_allowed=rows(CASH)))
        self.assertEqual(out["exclude_tenders"], [ONLINE])

    def test_the_store_credit_method_is_never_taken_off_so_an_exchange_goes_on(self):
        out = check(context(paid_by=(CASH,)))
        self.assertNotIn(CREDIT, out["exclude_tenders"])
        self.assertNotIn(CREDIT, check(context(paid_by=(VOUCHER,)))["exclude_tenders"])

    def test_none_of_the_sales_methods_offered_refuses_the_refund(self):
        out = check(context(paid_by=(VOUCHER,), offered=[CASH, CARD]))
        self.assertEqual(out, {"verdict": "refuse", "reason": "None of the methods that paid this sale can take its refund "
                                                              "here. Use Desk, or get a manager."})

    def test_nothing_to_take_off_is_a_plain_allow(self):
        self.assertEqual(check(context(paid_by=(CASH, CARD, ONLINE))), {"verdict": "allow"})

    def test_an_order_and_a_plan_refund_by_what_paid_into_them(self):
        for channel in ("order", "layaway"):
            self.assertEqual(check(context(channel=channel, paid_by=(CASH,)))["exclude_tenders"], [CARD, ONLINE], channel)

    def test_a_channel_it_does_not_know_is_judged_by_the_methods_that_paid(self):
        self.assertEqual(check(context(channel="voucher", paid_by=(CASH,)))["exclude_tenders"], [CARD, ONLINE])

    def test_the_rule_switched_off_lets_every_method_through(self):
        self.assertEqual(check(s=settings(same_methods=0)), {"verdict": "allow"})

    def test_a_method_offered_twice_is_named_once(self):
        out = check(context(offered=[CASH, CASH, CARD]))
        self.assertEqual(out["exclude_tenders"], [CASH])

    def test_more_methods_to_take_off_than_the_check_may_is_a_refusal(self):
        many = [f"M{i}" for i in range(25)] + [CARD]
        out = check(context(offered=many))
        self.assertEqual(out["verdict"], "refuse")
        self.assertLessEqual(len(check(context(offered=[f"M{i}" for i in range(20)] + [CARD]))["exclude_tenders"]), 20)


class WithoutItsSale(unittest.TestCase):
    def test_a_return_without_its_sale_goes_back_by_the_methods_named(self):
        out = check(context(channel="none"), s=settings(without_sale=rows(CASH)))
        self.assertEqual(out, {"verdict": "allow", "exclude_tenders": [CARD, ONLINE],
                               "reason": "Without its sale, refunded only by Cash, Store Credit."})

    def test_none_named_leaves_it_as_today(self):
        self.assertEqual(check(context(channel="none"), s=settings(without_sale=[])), {"verdict": "allow"})

    def test_none_of_the_named_methods_offered_refuses(self):
        out = check(context(channel="none", offered=[CASH, CARD]), s=settings(without_sale=rows(VOUCHER), store_credit=""))
        self.assertEqual(out["verdict"], "refuse")
        self.assertIn(VOUCHER, out["reason"])

    def test_the_same_methods_rule_does_not_touch_a_return_without_its_sale(self):
        self.assertEqual(check(context(channel="none"), s=settings(without_sale=[])), {"verdict": "allow"})


class NotJudged(unittest.TestCase):
    def test_a_sale_is_never_judged(self):
        self.assertEqual(check(context(stage="sale", lines=[line(qty=1)])), {"verdict": "allow"})

    def test_a_return_whose_money_goes_nowhere_is_not_judged(self):
        for grand in (0, 500):
            self.assertEqual(check(context(grand=grand)), {"verdict": "allow"}, grand)

    def test_no_settings_record_turns_every_rule_off(self):
        self.assertEqual(refunds.on_check(context(), None), {"verdict": "allow"})
        self.assertIsNone(refunds.settings_of(None))


class Settings(unittest.TestCase):
    def test_the_record_and_its_two_tables(self):
        s = refunds.settings_of(dict(DOC, always_allowed=rows(CASH, CASH, VOUCHER), without_sale=rows(CREDIT)))
        self.assertEqual(s, {"same_methods": True, "store_credit": CREDIT, "always": [CASH, VOUCHER],
                             "without_sale": [CREDIT]})

    def test_a_tick_reads_as_on_only_when_it_is(self):
        for v, want in ((1, True), ("1", True), (True, True), (0, False), (None, False), ("0", False)):
            self.assertEqual(refunds.settings_of(dict(DOC, same_methods=v))["same_methods"], want, repr(v))

    def test_a_row_without_a_method_is_left_out(self):
        s = refunds.settings_of(dict(DOC, always_allowed=[{"mode_of_payment": None}, {"x": 1}, "junk", {"mode_of_payment": CASH}]))
        self.assertEqual(s["always"], [CASH])

    def test_a_settings_answer_that_is_not_a_record_is_refused(self):
        for bad in ([], "x", 3):
            with self.assertRaises(ValueError):
                refunds.settings_of(bad)


class Context(unittest.TestCase):
    def body(self, ctx):
        return {"point": "check/1", "context": ctx}

    def test_a_good_return_and_a_sale_are_read(self):
        self.assertEqual(refunds.check_context(self.body(context()))["stage"], "return")
        sale = context(stage="sale")
        del sale["offered_tenders"]                  # a sale is answered at once: nothing else is read
        self.assertEqual(refunds.check_context(self.body(sale))["stage"], "sale")

    def test_a_bad_shape_is_refused_before_any_decision(self):
        bad = []
        for key, value in (("offered_tenders", None), ("offered_tenders", [1]), ("return_of", None),
                           ("totals", {"grand_minor": "1"}), ("totals", {"grand_minor": True})):
            ctx = context()
            ctx[key] = value
            bad.append(ctx)
        for key, value in (("paid_by", None), ("paid_by", [3]), ("channel", 1), ("invoice", None)):
            ctx = context()
            ctx["return_of"][key] = value
            bad.append(ctx)
        for ctx in bad:
            with self.assertRaises(ValueError):
                refunds.check_context(self.body(ctx))
        for body in ({"point": "check/2", "context": context()}, {"point": "check/1", "context": dict(context(), v=2)},
                     {"point": "check/1", "context": dict(context(), stage="refund")}, [], None):
            with self.assertRaises(ValueError):
                refunds.check_context(body)


class Words(unittest.TestCase):
    def test_every_sentence_is_plain_and_at_most_140(self):
        long = "S" * 300
        many = rows(*[f"Method {i} " + "x" * 30 for i in range(8)])
        outs = [check(context(channel="none"), s=settings(without_sale=rows("<b>Gift</b> " + long))),
                check(context(channel="none"), s=settings(without_sale=many)),
                check(context(channel="none", offered=["Z"]), s=settings(without_sale=many, store_credit="")),
                check(context(paid_by=(VOUCHER,), offered=[CASH])), check(),
                check(context(offered=[f"M{i}" for i in range(25)] + [CARD]))]
        for out in outs:
            reason = out.get("reason")
            self.assertTrue(reason and len(reason) <= 140 and "<" not in reason and ">" not in reason, out)
            self.assertTrue(all(ch.isprintable() for ch in reason))

    def test_the_marks_arabic_and_persian_text_carry_are_kept(self):
        self.assertEqual(refunds.plain("فرع‏ المول"), "فرع‏ المول")


class Verify(unittest.TestCase):
    def test_the_signature_and_the_time_are_checked(self):
        import base64, hashlib, hmac
        raw, ts = b'{"a":1}', "1000"
        sig = base64.b64encode(hmac.new(b"s", b"1000." + raw, hashlib.sha256).digest()).decode()
        self.assertEqual(refunds.verify(ts, sig, raw, "s", now=1000), "")
        self.assertTrue(refunds.verify(ts, sig, raw, "t", now=1000))
        self.assertTrue(refunds.verify(ts, sig, raw + b" ", "s", now=1000))
        self.assertTrue(refunds.verify(ts, sig, raw, "s", now=1400))
        padded = "0" * 9 + "1000"                       # 13 digits that read as the right time: refused, never parsed
        psig = base64.b64encode(hmac.new(b"s", padded.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        self.assertTrue(refunds.verify(padded, psig, raw, "s", now=1000))
        self.assertTrue(refunds.verify(None, sig, raw, "s", now=1000))


if __name__ == "__main__":
    unittest.main()
