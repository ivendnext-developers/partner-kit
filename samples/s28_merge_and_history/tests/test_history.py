"""S28 — the Customer history page: the context check, and the visits read for the context's customer only.

    python3 -m unittest discover -s samples/s28_merge_and_history/tests -p 'test_*.py'
"""

import time
import unittest

from fakes import CONF, FakeShop, app, context, history, sale

SALES = [
    sale("POS-1", "Ann", "2026-10-01", discount=5, pct=10, owner="cashier1@demo.example",
         items=[{"item_code": "EARBUDS", "item_name": "Earbuds", "qty": 2, "discount_amount": 1.5,
                 "discount_percentage": 5, "warehouse": "Store 1 - DR"},
                {"item_code": "CASE", "item_name": "Case", "qty": 1, "discount_amount": 0, "discount_percentage": 0,
                 "warehouse": "Store 1 - DR"}]),
    sale("POS-2", "Ann", "2026-10-03", owner="cashier2@demo.example", store="Store 2 - DR"),
    sale("SI-1", "Ann", "2026-10-02", doctype=history.SI, owner="admin@demo.example"),
    sale("SI-ROLL", "Ann", "2026-10-04", doctype=history.SI, is_consolidated=1),     # the day's roll-up: POS-1 again
    sale("POS-DRAFT", "Ann", "2026-10-05", docstatus=0),
    sale("POS-BOB", "Bob", "2026-10-06"),
]
USERS = {"cashier1@demo.example": "Casey One", "cashier2@demo.example": "Casey Two", "admin@demo.example": "Ada Admin"}


def service(settings=None, sales=SALES):
    shop = FakeShop(settings=settings, sales=sales, users=USERS)
    return app.Service(CONF, shop), shop


class Context(unittest.TestCase):
    def test_a_bad_signature_is_refused(self):
        svc, shop = service()
        code, out = svc.open({"ctx": context("Ann", secret="wrong")})
        self.assertEqual((code, shop.reads), (403, []))
        self.assertIn("signature", out["error"])

    def test_an_expired_context_is_refused(self):
        svc, shop = service()
        code, out = svc.open({"ctx": context("Ann", exp_in=-1)})
        self.assertEqual((code, shop.reads), (403, []))
        self.assertIn("run out", out["error"])

    def test_a_reused_nonce_is_refused(self):
        svc, _ = service()
        ctx = context("Ann")
        self.assertEqual(svc.open({"ctx": ctx})[0], 200)
        self.assertEqual(svc.open({"ctx": ctx})[0], 403)

    def test_a_tampered_payload_is_refused(self):
        body, sig = context("Ann").split(".")
        forged = history.b64(history._unb64(body).replace(b"Ann", b"Bob")) + "." + sig
        self.assertEqual(service()[0].open({"ctx": forged})[0], 403)


class Visits(unittest.TestCase):
    def test_the_till_shows_the_sales_customers_visits_newest_first_without_the_roll_up(self):
        code, out = service()[0].open({"ctx": context("Ann")})
        self.assertEqual((code, out["state"], out["on"]), (200, "ok", "till"))
        self.assertEqual([v["name"] for v in out["visits"]], ["POS-2", "SI-1", "POS-1"])

    def test_each_visit_has_the_store_who_served_and_the_discounts(self):
        v = {x["name"]: x for x in service()[0].open({"ctx": context("Ann")})[1]["visits"]}
        self.assertEqual((v["POS-2"]["store"], v["POS-2"]["served"]), ("Store 2 - DR", "Casey Two"))
        one = v["POS-1"]
        self.assertEqual((one["served"], one["sale_discount"], one["sale_discount_pct"], one["lines_discount"]),
                         ("Casey One", "5.00", "10", "3.00"))
        self.assertEqual(one["lines"][0], {"item": "Earbuds", "qty": "2", "discount_pct": "5", "discount": "3.00"})

    def test_the_same_day_sorts_by_time_as_numbers(self):
        early, late = {"name": "E", "customer": "Ann", "docstatus": 1, "posting_date": "2026-10-01", "posting_time": "9:05:00"}, \
            {"name": "L", "customer": "Ann", "docstatus": 1, "posting_date": "2026-10-01", "posting_time": "14:00:00"}
        self.assertEqual(history.pick([early, late], [], "Ann", 1), [(history.POS, "L")])

    def test_no_more_than_the_settings_number_is_read_or_shown(self):
        svc, shop = service(settings={"history_count": 2})
        out = svc.open({"ctx": context("Ann")})[1]
        self.assertEqual(len(out["visits"]), 2)
        self.assertTrue(all(n == 2 for _dt, _c, n in shop.reads))

    def test_the_count_defaults_to_ten_and_stops_at_fifty(self):
        self.assertEqual((history.count_of(None), history.count_of({"history_count": 0}),
                          history.count_of({"history_count": 500})), (10, 10, 50))

    def test_never_another_customers_sale(self):
        out = service()[0].open({"ctx": context("Ann")})[1]
        self.assertNotIn("POS-BOB", [v["name"] for v in out["visits"]])
        self.assertEqual(history.pick([{"name": "X", "customer": "Bob", "docstatus": 1}], [], "Ann", 10), [])

    def test_a_read_that_returns_another_customers_sale_is_dropped(self):
        svc, shop = service()
        shop.sales_rows["POS-2"]["customer"] = "Bob"            # the list said Ann; the record says Bob
        shop.sales = lambda dt, c, n: [{"name": "POS-2", "customer": "Ann", "docstatus": 1, "posting_date": "x"}] \
            if dt == history.POS else []
        self.assertEqual(svc.open({"ctx": context("Ann")})[1]["visits"], [])

    def test_a_sale_with_no_customer_shows_the_empty_state(self):
        code, out = service()[0].open({"ctx": context(None)})
        self.assertEqual((code, out["state"]), (200, "no_customer"))

    def test_a_customer_with_no_sales_shows_none(self):
        out = service()[0].open({"ctx": context("Zed")})[1]
        self.assertEqual((out["state"], out["visits"]), ("ok", []))

    def test_desk_opens_for_a_customer_record_only(self):
        svc, _ = service()
        out = svc.open({"ctx": context(desk=("Customer", "Ann"), nonce="d" * 32)})[1]
        self.assertEqual((out["on"], len(out["visits"])), ("desk", 3))
        out = svc.open({"ctx": context(desk=("Sales Order", "SO-1"), nonce="e" * 32)})[1]
        self.assertEqual(out["state"], "no_customer")

    def test_a_desk_page_with_no_record_is_desk(self):
        out = service()[0].open({"ctx": context(desk=("", ""), nonce="f" * 32)})[1]
        self.assertEqual((out["on"], out["state"]), ("desk", "no_customer"))

    def test_a_returns_discount_is_shown_as_taken_off(self):
        ret = sale("RET-1", "Ann", "2026-10-09", items=[{"item_code": "X", "item_name": "X", "qty": -2, "discount_amount": 1.5,
                                                         "discount_percentage": 5, "warehouse": "W"}])
        v = history.visit(history.POS, ret, {})
        self.assertEqual((v["lines"][0]["discount"], v["lines_discount"]), ("3.00", "3.00"))

    def test_the_page_answers_nothing_to_the_sale(self):
        src = open(app.__file__).read() + open(app.os.path.join(app.HERE, "history.html")).read()
        self.assertNotIn("page.submit", src)
        self.assertNotIn("ivendnext:done", src)

    def test_a_shop_that_cannot_be_read_says_so(self):
        svc, shop = service()

        def down(*a):
            raise app.ShopError("timed out")
        shop.sales = down
        code, out = svc.open({"ctx": context("Ann")})
        self.assertEqual(code, 502)
        self.assertIn("could not be read", out["error"])


if __name__ == "__main__":
    unittest.main()
