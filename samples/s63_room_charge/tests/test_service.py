"""S63's laptop tests: the stand-in hotel system runs as a real web server on this machine, and the till's calls go through the
service's own entry (``Service.handle``), signed as the till signs them.

    python3 -m unittest discover -s samples/s63_room_charge/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path[:0] = [HERE, os.path.join(SAMPLE, "service"), os.path.join(SAMPLE, "standin"), os.path.join(KIT, "tools", "contracts")]
import app  # noqa: E402
import hotel as H  # noqa: E402
import hotel_api as standin  # noqa: E402
import hotel_mews  # noqa: E402
import rooms  # noqa: E402
import worker  # noqa: E402
from check import errors  # noqa: E402  (the kit's contract checker)
from fake_shop import POST, SET, STORE, FakeFeed, FakeShop, hotel_shop, sale  # noqa: E402

SECRET = "check-secret"
MODE = "Room Charge"


def signed(body: dict, secret: str = SECRET) -> tuple[dict, bytes]:
    raw = json.dumps(body).encode()
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw


def ctx(room="412", guest="Smith", folio="", tip="", stage="sale", offered=("Cash", "Credit Card", MODE), return_of=None, store=STORE):
    details = [{"name": k, "value": v} for k, v in (("Room", room), ("Guest", guest), ("Folio", folio), ("Tip", tip)) if v]
    c = {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": "s1", "store": store, "pos_profile": "Bar",
         "company": "Harbour Hotel", "currency": "USD", "lang": "en", "operator": "server@hotel.example", "customer": "Walk-in",
         "customer_group": "Retail", "price_list": "Standard Selling", "coupon_codes": [], "sale_attributes": details,
         "lines": [{"line_no": 1, "item_code": "SOUP", "item_group": "Food", "qty_milli": 1000, "uom": "Nos", "rate_minor": 12000,
                    "amount_minor": 12000, "discount_minor": 0, "is_free_item": 0, "promo_qty_milli": 0, "line_attributes": []}],
         "totals": {"net_minor": 12000, "tax_minor": 0, "discount_minor": 0, "grand_minor": 12000},
         "offered_tenders": list(offered), "pos_opening": "O1", "pos_terminal": "T1"}
    if return_of is not None:
        c["return_of"] = return_of
    return c


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hotel = standin.Hotel()
        cls.srv = standin.make_server(cls.hotel, 0)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.sim = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.hotel.mode, self.hotel.posted, self.hotel.finds = "up", [], 0
        self.t = hotel_shop()
        self.svc = app.Service({"IVN_SHOP_URL": "https://hotel.example", "IVN_SHOP_KEY": "k:s", "IVN_CHECK_SECRET": SECRET,
                                "HOTEL_SIM_URL": self.sim}, opener=lambda *a: self.t)
        self.feed = FakeFeed()

    def ask(self, c):
        code, out = self.svc.handle("POST", app.ROUTE, *signed({"point": "check/1", "context": c}))
        self.assertEqual(code, 200, out)
        self.assertEqual(errors("partner_check", "answer", out), [], out)
        return out

    def run_pass(self, *events):
        self.feed.waiting += [{"id": f"e{i}-{time.monotonic()}", "doc_type": "POS Invoice", "event": e, "doc_name": n} for i, (e, n) in enumerate(events)]
        return worker.Pass(self.svc, self.t, self.feed).run()

    def row(self, name):
        return self.t.db[POST].get(name)


class TheCheckAtPay(Base):
    def test_a_room_that_fits_fills_the_folio(self):
        self.assertEqual(self.ask(ctx()), {"verdict": "allow", "fill": {"Folio": "R-1001 (412 Smith)"}})

    def test_the_filled_sale_gets_the_same_answer_without_calling_the_hotel(self):
        first = self.ask(ctx())
        before = self.hotel.finds
        self.assertEqual(self.ask(ctx(folio=first["fill"]["Folio"])), first)
        self.assertEqual(self.hotel.finds, before)

    def test_a_room_corrected_after_the_check_is_looked_up_again(self):
        out = self.ask(ctx(room="6A", guest="Khan", folio="R-1001 (412 Smith)"))
        self.assertEqual(out["fill"]["Folio"], "R-1003 (6A Khan)")

    def test_no_room_dims_the_tile_and_never_asks(self):
        out = self.ask(ctx(room="", guest=""))
        self.assertEqual((out["verdict"], out["exclude_tenders"]), ("allow", [MODE]))
        self.assertIn("Sale details", out["reason"])
        self.hotel.mode = "down"
        self.assertEqual(self.ask(ctx(room="", guest=""))["verdict"], "allow")

    def test_a_room_with_no_surname_dims_the_tile(self):
        self.assertEqual(self.ask(ctx(guest=""))["exclude_tenders"], [MODE])

    def test_a_wrong_name_dims_the_tile_with_its_reason(self):
        out = self.ask(ctx(guest="Brown"))
        self.assertEqual(out, {"verdict": "allow", "exclude_tenders": [MODE], "reason": "Room 412 has no guest named Brown."})

    def test_a_guest_who_may_not_charge_dims_the_tile(self):
        self.assertIn("can't take charges", self.ask(ctx(room="518", guest="Jones"))["reason"])

    def test_the_hotel_down_with_a_room_typed_asks(self):
        self.hotel.mode = "down"
        self.assertEqual(self.ask(ctx()), {"verdict": "ask", "question": "The hotel system isn't answering. Charge room 412 anyway?"})

    def test_a_tile_not_offered_is_never_named(self):
        self.assertEqual(self.ask(ctx(room="", guest="", offered=("Cash",))), {"verdict": "allow"})

    def test_a_tip_that_is_not_an_amount_dims_the_tile(self):
        self.assertIn("not an amount", self.ask(ctx(tip="ten"))["reason"])

    def test_a_store_with_no_row_is_left_alone(self):
        self.assertEqual(self.ask(ctx(store="Other Store")), {"verdict": "allow"})

    def test_a_row_for_a_system_not_set_up_says_so(self):
        self.t.db[SET][SET]["stores"][0]["hotel_system"] = "Other"
        self.assertIn("isn't set up", self.ask(ctx())["reason"])

    def test_the_hotel_call_is_capped_at_a_second_and_a_half(self):
        with mock.patch.object(H, "adapter", wraps=H.adapter) as a:
            self.ask(ctx())
        self.assertEqual(a.call_args.args[2], 1.5)

    def test_an_unsigned_call_is_refused(self):
        h, raw = signed({"point": "check/1", "context": ctx()}, secret="wrong")
        self.assertEqual(self.svc.handle("POST", app.ROUTE, h, raw)[0], 401)

    def test_the_shop_unreadable_takes_the_down_answer(self):
        self.t.down = True
        self.assertEqual(self.svc.handle("POST", app.ROUTE, *signed({"point": "check/1", "context": ctx()}))[0], 503)


class ReturnsAtTheTill(Base):
    def r(self, paid_by, offered=("Cash", "Credit Card", "Store Credit", MODE)):
        return ctx(stage="return", offered=offered, return_of={"invoice": "S1", "channel": "pos", "paid_by": list(paid_by)})

    def test_a_room_charge_goes_back_to_the_room(self):
        out = self.ask(self.r([MODE]))
        self.assertEqual(out["exclude_tenders"], ["Cash", "Credit Card", "Store Credit"])
        self.assertIn("Return it and ring it again", out["reason"])

    def test_a_splits_card_keeps_its_share(self):
        self.assertEqual(self.ask(self.r([MODE, "Credit Card"]))["exclude_tenders"], ["Cash", "Store Credit"])

    def test_a_sale_not_on_a_room_is_left_alone(self):
        self.assertEqual(self.ask(self.r(["Cash"])), {"verdict": "allow"})

    def test_nothing_to_dim_sends_no_list(self):
        self.assertEqual(self.ask(self.r([MODE], offered=(MODE,))), {"verdict": "allow"})

    def test_a_return_is_never_refused_or_asked(self):
        self.hotel.mode = "down"
        self.assertEqual(self.ask(self.r([MODE]))["verdict"], "allow")


class ThePost(Base):
    def test_a_sale_posts_and_keeps_the_reference(self):
        sale(self.t, "S1")
        self.run_pass(("sale.booked", "S1"))
        row = self.row("S1")
        self.assertEqual((row["status"], row["folio"], row["amount"]), ("Posted", "R-1001", 120.0))
        self.assertEqual(row["posted_on"], worker.datetime.date.today().isoformat())
        self.assertTrue(row["charge_reference"].startswith("L-"))
        self.assertEqual([(p["folio"], p["amount"], p["code"], p["receipt"]) for p in self.hotel.posted], [("R-1001", 120.0, "FNB", "S1")])

    def test_a_post_delivered_twice_books_once(self):
        sale(self.t, "S1")
        self.run_pass(("sale.booked", "S1"))
        self.run_pass(("sale.booked", "S1"), ("sale.booked", "S1"))
        self.assertEqual(len(self.hotel.posted), 1)
        self.assertEqual(self.row("S1")["status"], "Posted")
        self.assertEqual((self.feed.waiting, self.feed.notes), ([], {}))

    def test_the_row_says_sending_before_the_hotel_is_called(self):
        sale(self.t, "S1")
        seen = []
        real = H.Simulator.post
        with mock.patch.object(H.Simulator, "post", lambda s, *a: seen.append(self.row("S1")["status"]) or real(s, *a)):
            self.run_pass(("sale.booked", "S1"))
        self.assertEqual(seen, ["Sending"])

    def test_a_crash_mid_call_goes_to_the_auditor_and_is_not_sent_again(self):
        sale(self.t, "S1")
        with mock.patch.object(H.Simulator, "post", side_effect=SystemError("the worker died")):
            self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.row("S1")["status"], "Sending")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual((self.row("S1")["status"], self.hotel.posted), ("Refused", []))
        self.assertIn("Check the folio", self.row("S1")["message"])

    def test_the_hotel_down_waits_and_catches_up_once(self):
        sale(self.t, "S1")
        self.hotel.mode = "down"
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.row("S1")["status"], "Waiting")
        self.run_pass()
        self.assertEqual(self.row("S1")["status"], "Waiting")
        self.hotel.mode = "up"
        self.run_pass()
        self.run_pass()
        self.assertEqual((self.row("S1")["status"], len(self.hotel.posted)), ("Posted", 1))

    def test_a_lost_answer_goes_to_the_auditor_and_is_not_sent_twice(self):
        sale(self.t, "S1")
        self.hotel.mode = "lost"
        self.run_pass(("sale.booked", "S1"))
        self.hotel.mode = "up"
        self.run_pass()
        self.assertEqual((self.row("S1")["status"], len(self.hotel.posted)), ("Refused", 1))

    def test_a_gateways_502_goes_to_the_auditor_and_is_not_sent_twice(self):
        sale(self.t, "S1")
        self.hotel.mode = "gateway"
        self.run_pass(("sale.booked", "S1"))
        self.hotel.mode = "up"
        self.run_pass()
        self.assertEqual((self.row("S1")["status"], len(self.hotel.posted)), ("Refused", 1))

    def test_a_crash_during_a_resend_goes_to_the_auditor(self):
        sale(self.t, "S1")
        self.hotel.mode = "down"
        self.run_pass(("sale.booked", "S1"))
        self.hotel.mode = "up"
        with mock.patch.object(H.Simulator, "post", side_effect=SystemError("the worker died")), self.assertRaises(SystemError):
            self.run_pass()
        self.assertEqual(self.row("S1")["status"], "Sending")
        self.run_pass()
        self.assertEqual((self.row("S1")["status"], self.hotel.posted), ("Refused", []))

    def test_a_429_waits(self):
        sale(self.t, "S1")
        with mock.patch.object(H.Simulator, "post", side_effect=H.HotelDown("answered 429")):
            self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.row("S1")["status"], "Waiting")
        self.assertIn("429", self.row("S1")["message"])

    def test_a_store_that_named_its_tile_differently_posts_and_checks(self):
        self.t.db[SET][SET]["stores"][0]["mode_of_payment"] = "Hotel Room"
        sale(self.t, "S1", paid=(("Hotel Room", 80.0),))
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([p["amount"] for p in self.hotel.posted], [80.0])
        self.assertEqual(self.ask(ctx(guest="Brown", offered=("Cash", "Hotel Room")))["exclude_tenders"], ["Hotel Room"])

    def test_a_sale_already_cancelled_when_read_is_not_posted(self):
        sale(self.t, "S1")["docstatus"] = 2
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.hotel.posted, [])

    def test_a_tip_that_only_looks_like_decimals_dims_the_tile(self):
        self.assertIn("not an amount", self.ask(ctx(tip="50,000"))["reason"])
        self.assertIn("fill", self.ask(ctx(tip="12,50")))

    def test_the_guests_name_with_brackets_keeps_its_folio(self):
        first = self.ask(ctx(room="6A", guest="Khan"))["fill"]["Folio"]
        text = rooms.folio_text("R-1", "412", "Smith (Jr)")
        self.assertTrue(rooms.folio_fits(text, "412", "Smith (Jr)"))
        self.assertEqual(rooms.folio_id(text), "R-1")
        self.assertEqual(first, "R-1003 (6A Khan)")

    def test_the_hotel_refusing_goes_to_the_auditor(self):
        sale(self.t, "S1", folio="R-9999 (412 Smith)")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.row("S1")["status"], "Refused")
        self.assertIn("no longer staying", self.row("S1")["message"])

    def test_a_split_posts_only_its_share(self):
        sale(self.t, "S1", paid=((MODE, 70.0), ("Credit Card", 50.0)))
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([p["amount"] for p in self.hotel.posted], [70.0])

    def test_a_sale_with_no_room_charge_writes_nothing(self):
        sale(self.t, "S1", paid=(("Cash", 120.0),))
        self.run_pass(("sale.booked", "S1"))
        self.assertIsNone(self.t.db.get(POST, {}).get("S1"))

    def test_a_blank_folio_is_looked_up_at_post_time(self):
        sale(self.t, "S1", folio="")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual((self.row("S1")["status"], self.row("S1")["folio"]), ("Posted", "R-1001"))

    def test_a_folio_for_another_room_is_never_used(self):
        sale(self.t, "S1", room="6A", guest="Khan", folio="R-1001 (412 Smith)")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.hotel.posted[0]["folio"], "R-1003")

    def test_a_blank_folio_with_no_room_or_match_is_refused(self):
        sale(self.t, "S1", room="", guest="", folio="")
        sale(self.t, "S2", guest="Brown", folio="")
        self.run_pass(("sale.booked", "S1"), ("sale.booked", "S2"))
        self.assertEqual((self.row("S1")["status"], self.row("S2")["status"]), ("Refused", "Refused"))
        self.assertEqual(self.hotel.posted, [])

    def test_the_tip_posts_on_its_own_code(self):
        sale(self.t, "S1", tip="12.50")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["code"], p["amount"]) for p in self.hotel.posted], [("charge", "FNB", 120.0), ("tip", "TIP", 12.5)])
        self.assertTrue(self.row("S1")["tip_reference"].startswith("L-"))

    def test_a_tip_rung_on_the_chip_reaches_the_folio(self):
        sale(self.t, "S1", chip=((MODE, 20.0),))
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 120.0), ("tip", 20.0)])

    def test_a_tip_on_the_chip_and_the_detail_is_posted_once(self):
        sale(self.t, "S1", chip=((MODE, 20.0),), tip="7.50")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 120.0), ("tip", 20.0)])
        self.assertEqual((self.row("S1")["tip"], self.row("S1")["clearing"]), (20.0, 140.0))

    def test_a_typed_tip_beside_a_card_payers_chip_tip_is_not_the_guests(self):
        sale(self.t, "S1", paid=(("Credit Card", 50.0), (MODE, 70.0)), chip=(("Credit Card", 9.0),), tip="9")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 70.0)])
        self.assertEqual(self.row("S1")["clearing"], 70.0)

    def test_a_typed_detail_tip_is_on_the_folio_but_not_in_clearing(self):
        sale(self.t, "S1", tip="7.50")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual((self.row("S1")["tip"], self.row("S1")["clearing"]), (7.5, 120.0))

    def test_a_chip_tip_waits_with_its_charge_and_goes_once_when_the_hotel_answers(self):
        sale(self.t, "S1", chip=((MODE, 20.0),))
        self.hotel.mode = "down"
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual(self.row("S1")["status"], "Waiting")
        self.hotel.mode = "up"
        self.run_pass()
        self.run_pass()
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 120.0), ("tip", 20.0)])

    def test_a_return_of_a_chip_tipped_sale_takes_off_only_its_charge(self):
        sale(self.t, "S1", paid=((MODE, 70.0),), chip=((MODE, 10.0),))
        self.run_pass(("sale.booked", "S1"))
        sale(self.t, "R1", paid=((MODE, -70.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 70.0), ("tip", 10.0), ("charge", -70.0)])
        self.assertEqual(self.row("R1")["clearing"], -70.0)

    def test_a_cancelled_chip_tipped_sale_says_its_tip_stays(self):
        sale(self.t, "S1", chip=((MODE, 20.0),))
        self.run_pass(("sale.cancelled", "S1"))
        self.assertEqual((self.row("S1")["status"], self.row("S1")["clearing"]), ("Refused", 140.0))
        self.assertIn("stays booked", self.row("S1")["message"])

    def test_the_detail_tip_still_posts_when_no_chip_tip_was_rung(self):
        sale(self.t, "S1", tip="7.50")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 120.0), ("tip", 7.5)])

    def test_a_split_posts_only_the_room_charge_legs_own_tip(self):
        # the till lane's walk: card 10.00 with a 1.00 tip, Room Charge 11.78 with a 2.36 tip (sale tip 3.36)
        sale(self.t, "S1", paid=(("Credit Card", 10.0), (MODE, 11.78)), chip=(("Credit Card", 1.0), (MODE, 2.36)))
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 11.78), ("tip", 2.36)])

    def test_a_card_payers_chip_tip_never_reaches_the_folio(self):
        sale(self.t, "S1", paid=(("Credit Card", 50.0), (MODE, 70.0)), chip=(("Credit Card", 9.0),))
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 70.0)])

    def test_only_the_legs_live_tip_journal_counts(self):
        sale(self.t, "S1", chip=((MODE, 20.0),))
        self.t.put("Journal Entry", "JV-cancelled", docstatus=2, custom_reference_1="S1", custom_reference_2="Tip",
                   custom_reference_3=MODE, total_debit=20.0)
        self.t.put("Journal Entry", "JV-other", docstatus=1, custom_reference_1="S1", custom_reference_2="Payer",
                   custom_reference_3=MODE, total_debit=99.0)
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 120.0), ("tip", 20.0)])

    def test_a_site_not_yet_updated_posts_the_detail_tip(self):
        sale(self.t, "S1", chip=((MODE, 20.0),), tip="20")
        real = self.t.list

        def refuse(dt, *a, **k):
            if dt == "Journal Entry":
                raise worker.ShopError(403, "not permitted")
            return real(dt, *a, **k)
        self.t.list = refuse
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 120.0), ("tip", 20.0)])
        self.assertEqual(self.row("S1")["status"], "Posted")

    def test_no_tip_code_posts_no_tip(self):
        self.t.db[SET][SET]["stores"][0]["tip_code"] = ""
        sale(self.t, "S1", tip="5")
        self.run_pass(("sale.booked", "S1"))
        self.assertEqual([p["kind"] for p in self.hotel.posted], ["charge"])

    def test_other_events_are_marked_done_unread(self):
        self.feed.waiting = [{"id": "x", "doc_type": "Sales Invoice", "event": "invoice.booked", "doc_name": "ROLLUP-1"},
                             {"id": "y", "doc_type": "POS Invoice", "event": "pos_invoice.on_update", "doc_name": "S9"}]
        worker.Pass(self.svc, self.t, self.feed).run()
        self.assertEqual(self.feed.waiting, [])

    def test_a_read_that_fails_leaves_the_event_with_a_note(self):
        self.feed.waiting = [{"id": "x", "doc_type": "POS Invoice", "event": "sale.booked", "doc_name": "S1"}]
        with mock.patch.object(FakeShop, "get", side_effect=ValueError("boom")):
            p = worker.Pass.__new__(worker.Pass)
            p.svc, p.t, p.feed, p.table, p.stores, p.count = self.svc, self.t, self.feed, POST, {}, {}
            p.read_feed()
        self.assertIn("x", self.feed.notes)
        self.assertEqual(len(self.feed.waiting), 1)


class ReturnsAndCancels(Base):
    def posted_sale(self, **k):
        sale(self.t, "S1", **k)
        self.run_pass(("sale.booked", "S1"))

    def test_a_return_posts_a_negative_line_to_the_same_folio(self):
        self.posted_sale()
        sale(self.t, "R1", folio="", paid=((MODE, -120.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual([(p["amount"], p["folio"]) for p in self.hotel.posted], [(120.0, "R-1001"), (-120.0, "R-1001")])
        self.assertEqual(self.row("R1")["status"], "Posted")

    def test_a_return_posts_only_its_own_room_charge_row_and_the_tip_stays(self):
        self.posted_sale(paid=((MODE, 70.0), ("Credit Card", 50.0)), tip="5")
        sale(self.t, "R1", paid=((MODE, -70.0), ("Credit Card", -50.0)), is_return=1, against="S1", tip="5")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual([(p["kind"], p["amount"]) for p in self.hotel.posted], [("charge", 70.0), ("tip", 5.0), ("charge", -70.0)])

    def test_two_partial_returns_are_two_rows_and_two_lines(self):
        self.posted_sale()
        sale(self.t, "R1", paid=((MODE, -20.0),), is_return=1, against="S1")
        sale(self.t, "R2", paid=((MODE, -30.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"), ("return.booked", "R2"))
        self.assertEqual([p["amount"] for p in self.hotel.posted], [120.0, -20.0, -30.0])

    def test_a_guest_who_moved_room_is_charged_back_on_the_first_folio(self):
        self.posted_sale()
        sale(self.t, "R1", room="", guest="", folio="", paid=((MODE, -120.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual(self.hotel.posted[-1]["folio"], "R-1001")

    def test_the_return_of_a_lost_sale_does_not_say_nothing_to_take_off(self):
        self.hotel.mode = "lost"
        self.posted_sale()
        self.hotel.mode = "up"
        sale(self.t, "R1", paid=((MODE, -120.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual(self.row("R1")["status"], "Refused")
        self.assertIn("take this amount off", self.row("R1")["message"])

    def test_a_cancel_keeps_the_check_the_folio_warning(self):
        self.hotel.mode = "lost"
        self.posted_sale()
        self.hotel.mode = "up"
        self.run_pass(("sale.cancelled", "S1"))
        self.assertIn("Cancelled in Desk", self.row("S1")["message"])
        self.assertIn("Check the folio", self.row("S1")["message"])

    def test_a_return_with_no_room_charge_row_posts_nothing(self):
        self.posted_sale()
        sale(self.t, "R1", paid=(("Cash", -120.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual(len(self.hotel.posted), 1)

    def test_a_return_waits_for_its_sale(self):
        self.hotel.mode = "down"
        self.posted_sale()
        sale(self.t, "R1", paid=((MODE, -120.0),), is_return=1, against="S1")
        self.hotel.mode = "up"
        self.t.db[POST]["S1"]["status"] = "Waiting"
        with mock.patch.object(worker.Pass, "rows", return_value=[]):
            self.run_pass(("return.booked", "R1"))
        self.assertEqual(self.row("R1")["status"], "Waiting")
        self.run_pass()
        self.assertEqual([p["amount"] for p in self.hotel.posted], [120.0, -120.0])

    def test_the_return_of_a_refused_sale_is_refused(self):
        self.posted_sale(folio="R-9999 (412 Smith)")
        sale(self.t, "R1", paid=((MODE, -120.0),), is_return=1, against="S1")
        self.run_pass(("return.booked", "R1"))
        self.assertEqual((self.row("R1")["status"], self.hotel.posted), ("Refused", []))

    def test_a_cancelled_sale_lands_on_refused_with_no_call(self):
        sale(self.t, "S1")
        self.run_pass(("sale.cancelled", "S1"))
        self.assertEqual((self.row("S1")["status"], self.hotel.posted), ("Refused", []))
        self.assertIn("Cancelled in Desk", self.row("S1")["message"])
        self.assertIn("no entry", self.row("S1")["message"])

    def test_a_waiting_sale_cancelled_is_not_sent(self):
        self.hotel.mode = "down"
        self.posted_sale()
        self.hotel.mode = "up"
        self.run_pass(("sale.cancelled", "S1"))
        self.run_pass()
        self.assertEqual((self.row("S1")["status"], self.hotel.posted), ("Refused", []))

    def test_a_posted_sale_cancelled_names_the_folio_line(self):
        self.posted_sale()
        self.run_pass(("sale.cancelled", "S1"))
        self.assertIn("take it off", self.row("S1")["message"])


class MewsAdapter(unittest.TestCase):
    S = {"system": "Mews", "connection": "client_token=c\naccess_token=a\nservice_id=svc\nenvironment=demo", "charge_code": "cat"}

    def api(self, answers):
        calls = []

        def fake(url, body, timeout, headers=None):
            op = url.split("/connector/v1/")[1]
            calls.append((op, body))
            got = answers[op]
            if isinstance(got, Exception):
                raise got
            return got if isinstance(got, tuple) else (200, got)
        return calls, mock.patch.object(hotel_mews, "call_json", fake)

    def rooms(self, classes=(), state="Started", last="Smith"):
        return {"resources/getAll": {"Resources": [{"Id": "r1", "Name": "412"}]},
                "customers/search": {"Customers": [{"Customer": {"Id": "c1", "LastName": last, "Classifications": list(classes)},
                                                    "Reservation": {"Id": "res1", "State": state}}]}}

    def test_finds_a_staying_guest_by_room_and_surname(self):
        _, p = self.api(self.rooms(last="SMITH"))
        with p:
            self.assertEqual(hotel_mews.Mews({}, self.S, 1.5).find("412", "smith"), "res1")

    def test_a_guest_on_the_no_post_list_is_refused_at_the_check(self):
        _, p = self.api(self.rooms(classes=["Cashlist"]))
        with p, self.assertRaises(H.NoGuest):
            hotel_mews.Mews({}, self.S, 1.5).find("412", "Smith")

    def test_a_guest_who_is_not_staying_is_no_match(self):
        _, p = self.api(self.rooms(state="Processed"))
        with p, self.assertRaises(H.NoGuest):
            hotel_mews.Mews({}, self.S, 1.5).find("412", "Smith")

    def post_answers(self, classes=(), state="Started"):
        return {"reservations/getAll/2023-06-06": {"Reservations": [{"Id": "res1", "State": state, "AccountId": "c1"}]},
                "customers/getAll": {"Customers": [{"Id": "c1", "Classifications": list(classes)}]}, "orders/add": {"OrderId": "o1"}}

    LINES = [{"kind": "charge", "code": "cat", "amount": -70.0, "label": "Restaurant charge"}]

    def test_posts_the_order_linked_to_the_reservation_with_the_receipt(self):
        calls, p = self.api(self.post_answers())
        with p:
            self.assertEqual(hotel_mews.Mews({}, self.S, 10).post("res1", self.LINES, "S1", "USD"), ["o1#1"])
        body = calls[-1][1]
        self.assertEqual((body["AccountId"], body["LinkedReservationId"], body["ServiceId"], body["Notes"]), ("c1", "res1", "svc", "Receipt S1"))
        self.assertEqual(body["Items"][0]["UnitAmount"]["GrossValue"], -70.0)
        self.assertEqual(body["Items"][0]["AccountingCategoryId"], "cat")

    def test_no_post_and_checked_out_are_refused_at_the_post_with_no_order(self):
        for answers in (self.post_answers(classes=["Cashlist"]), self.post_answers(state="Processed")):
            calls, p = self.api(answers)
            with p, self.assertRaises(H.HotelRefused):
                hotel_mews.Mews({}, self.S, 10).post("res1", self.LINES, "S1", "USD")
            self.assertNotIn("orders/add", [c[0] for c in calls])

    def test_a_token_the_hotel_can_fix_waits(self):
        answers = self.post_answers()
        answers["reservations/getAll/2023-06-06"] = (401, {"Message": "bad token"})
        _, p = self.api(answers)
        with p, self.assertRaises(H.HotelDown):
            hotel_mews.Mews({}, self.S, 10).post("res1", self.LINES, "S1", "USD")

    def test_an_order_whose_answer_was_lost_is_lost(self):
        answers = self.post_answers()
        answers["orders/add"] = H.HotelLost("cut")
        _, p = self.api(answers)
        with p, self.assertRaises(H.HotelLost):
            hotel_mews.Mews({}, self.S, 10).post("res1", self.LINES, "S1", "USD")

    def test_a_lost_answer_to_a_question_is_only_down(self):
        answers = self.rooms()
        answers["resources/getAll"] = H.HotelLost("cut")
        _, p = self.api(answers)
        with p, self.assertRaises(H.HotelDown):
            hotel_mews.Mews({}, self.S, 1.5).find("412", "Smith")

    def test_a_403_is_mews_own_refusal_and_goes_to_the_auditor(self):
        answers = self.post_answers()
        answers["orders/add"] = (403, {"Message": "The bill is closed."})
        _, p = self.api(answers)
        with p, self.assertRaisesRegex(H.HotelRefused, "The bill is closed"):
            hotel_mews.Mews({}, self.S, 10).post("res1", self.LINES, "S1", "USD")

    def test_a_room_typed_in_another_case_is_found(self):
        answers = self.rooms()
        answers["resources/getAll"] = {"Resources": [{"Id": "r1", "Name": "6A"}]}
        _, p = self.api(answers)
        with p:
            self.assertEqual(hotel_mews.Mews({}, self.S, 1.5).find("6a", "Smith"), "res1")

    def test_the_demo_environment_uses_the_demo_address(self):
        calls = []
        with mock.patch.object(hotel_mews, "call_json", lambda url, *a, **k: calls.append(url) or (200, {"Resources": []})):
            with self.assertRaises(H.NoGuest):
                hotel_mews.Mews({}, self.S, 1.5).find("412", "Smith")
        self.assertTrue(calls[0].startswith("https://api.mews-demo.com/"))

    def test_a_missing_connection_says_what_it_needs(self):
        with self.assertRaises(H.HotelRefused):
            hotel_mews.Mews({}, {"connection": "client_token=c"}, 1.5)


class PassesNeverOverlap(Base):
    def test_a_shop_still_in_its_pass_is_not_started_again(self):
        busy = {"-": mock.Mock(is_alive=lambda: True)}
        with mock.patch.object(worker, "one_pass", side_effect=AssertionError("ran twice")):
            out = worker.pass_all(self.svc, busy=busy)
        self.assertEqual(out, {"-": {"busy": True}})


class TheManifest(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(SAMPLE, "manifest.json")) as f:
            self.m = json.load(f)

    def test_the_details_are_plain_shared_words_and_none_is_required(self):
        self.assertEqual([a["name"] for a in self.m["sale_attributes"]], ["Room", "Guest", "Folio", "Tip"])
        self.assertFalse(any(a.get("required") for a in self.m["sale_attributes"]))

    def test_the_check_fills_only_the_folio_and_never_holds_a_sale(self):
        sub = self.m["extension_subscriptions"][0]
        self.assertEqual((sub["settings"], sub["down_answer"]), ({"fill_attributes": ["Folio"]}, "allow_and_flag"))

    def test_the_three_cards_are_on_the_workspace_and_an_update_names_them_all(self):
        cards = sorted(c["name"] for c in self.m["number_cards"])
        ws = self.m["workspaces"][0]
        self.assertEqual(sorted(r["number_card_name"] for r in ws["number_cards"]), cards)
        self.assertEqual(sorted(b["data"]["number_card_name"] for b in ws["blocks"] if b["type"] == "number_card"), cards)
        self.assertEqual(len(cards), 3)
        self.assertNotIn("dashboards", self.m)
        self.assertNotIn("dashboard_charts", self.m)
        self.assertNotIn("Dashboard", [s["type"] for s in ws["shortcuts"]])

    def test_the_post_row_is_named_by_its_sale(self):
        post = [d for d in self.m["doctypes"] if d["name"] == POST][0]
        self.assertEqual(post["autoname"], "field:sale")

    def test_the_report_has_no_total_of_the_rows_loaded(self):   # the day's sum is Group By, done by the database
        self.assertFalse(any(r.get("add_total_row") for r in self.m["reports"]))
        para = [b["data"]["text"] for b in self.m["workspaces"][0]["blocks"] if b["type"] == "paragraph"][0]
        self.assertIn("Group By Posted on with Sum of Clearing", para)

    def test_w1_desk_shows_the_staff_plain_words(self):   # F-HOSP-4
        (en,) = [t["words"] for t in self.m["translations"] if t["language"] == "en"]
        seen = {d["name"] for d in self.m["doctypes"]}
        for key in ("reports", "workspaces", "number_cards", "print_formats", "registered_applications"):
            seen |= {x["name"] for x in self.m.get(key) or []}
        seen |= {r for a in self.m.get("desk_actions") or [] for r in a.get("roles") or []} | {"PP RMC Auditor"}
        self.assertEqual(sorted(seen - set(en)), [])
        self.assertTrue(all(w and not w.startswith(self.m["prefix"]) for w in en.values()))


if __name__ == "__main__":
    unittest.main()
