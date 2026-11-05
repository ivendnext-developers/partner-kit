"""S39's service against a stand-in shop: signed calls on each route, the reads it makes, the dispensing it reserves (and
the one it keeps when Pay is pressed again), the statuses the shop gives back, two tills on one fill, the Desk chain, a
shop that cannot be read, and the real web server."""
import base64
import hashlib
import hmac
import json
import sys
import threading
import time
import unittest
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "service"), str(HERE.parent), str(HERE)]
import app  # noqa: E402
import rxrules as RX  # noqa: E402
import rxrules  # noqa: E402
from fake_shop import FakeShop  # noqa: E402

P = "PP RXC"
KEYS = ("dispensary", "front", "desk_order", "desk_delivery", "desk_invoice")
CONF = dict({f"IVN_SECRET_{k.upper()}": f"secret-{k}" for k in KEYS}, IVN_SHOP_URL="https://shop.example", IVN_SHOP_KEY="k:s")
FILLED = {"verdict": "fill", "fields": {"pp_rxc_rx_date": "2026-10-20"}}     # the Desk's answer: the prescription's date
NOW = time.mktime((2026, 10, 22, 12, 0, 0, 0, 0, 0)) - time.timezone      # noon UTC, 22 Oct 2026


def sign(raw: bytes, secret: str, ts=None):
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}


def till_body(lines, customer="Ann", rx=None, sale_ref="sale-1", operator="ph@shop", stage="sale", return_of=None,
              opening="DAY-1", details=None):
    attrs = [{"name": f"{P} Rx Number", "value": rx}] if rx else []
    attrs += [{"name": f"{P} {k}", "value": v} for k, v in (details or {}).items()]
    ctx = {"v": 1, "point": "check", "stage": stage, "currency_exponent": 2, "sale_ref": sale_ref, "store": "Dispensary - S",
           "pos_profile": "Dispensary", "company": "Shop", "currency": "KES", "lang": "en", "operator": operator,
           "customer": customer, "customer_group": "Individual", "price_list": "Standard Selling", "coupon_codes": [],
           "pos_opening": opening, "pos_terminal": "T1", "sale_attributes": attrs,
           "lines": [{"line_no": i + 1, "item_code": c, "item_group": g, "qty_milli": int(q * 1000), "uom": "Nos",
                      "rate_minor": 100, "amount_minor": int(q * 100), "discount_minor": 0, "line_attributes": []}
                     for i, (c, g, q) in enumerate(lines)],
           "totals": {"net_minor": 0, "tax_minor": 0, "discount_minor": 0, "grand_minor": 0}, "offered_tenders": ["Cash"]}
    if return_of:
        ctx["return_of"] = {"invoice": return_of, "channel": "pos", "paid_by": ["Cash"]}
    return {"point": "check/1", "context": ctx}


def desk_body(doctype, name, items, customer="Ann", rx="", user="ph@shop", is_return=0, against="", rx_date=""):
    return {"point": "doccheck/1", "context": {"v": 1, "event": "submit", "doctype": doctype, "name": name, "user": user,
            "company": "Shop", "lang": "en",
            "fields": {"name": name, "customer": customer, "pp_rxc_rx_number": rx, "pp_rxc_rx_date": rx_date,
                       "is_return": is_return,
                       "return_against": against, "items": items}}}


class Base(unittest.TestCase):
    def setUp(self):
        self.shop = FakeShop().pharmacy()
        self.svc = app.Service(CONF, api=self.shop, now=lambda: NOW)

    def call(self, route, body, secret=None):
        raw = json.dumps(body).encode()
        key = app.ROUTES[route][0]
        return self.svc.handle("POST", route, sign(raw, secret or f"secret-{key}"), raw)

    def sell(self, *lines, route="/rxc/dispensary", **k):
        return self.call(route, till_body(list(lines), **k))


class Calls(Base):
    def test_each_route_takes_only_its_own_secret(self):
        body = till_body([("BREAD", "Food", 1)])
        self.assertEqual(self.call("/rxc/dispensary", body)[0], 200)
        self.assertEqual(self.call("/rxc/dispensary", body, secret="secret-front")[0], 401)
        self.assertEqual(self.svc.handle("POST", "/rxc/nowhere", {}, b"{}")[0], 404)

    def test_a_stale_timestamp_is_refused(self):
        raw = json.dumps(till_body([("BREAD", "Food", 1)])).encode()
        self.assertEqual(self.svc.handle("POST", "/rxc/front", sign(raw, "secret-front", time.time() - 3600), raw)[0], 401)

    def test_a_desk_route_takes_only_its_record_type(self):
        body = desk_body("Sales Invoice", "SI-1", [{"item_code": "BREAD", "item_group": "Food", "stock_qty": 1000}])
        self.assertEqual(self.call("/rxc/desk/order", body)[0], 400)
        self.assertEqual(self.call("/rxc/desk/invoice", body), (200, {"verdict": "allow"}))

    def test_a_shop_that_cannot_be_read_is_503_so_the_down_answer_applies(self):
        self.shop.fail = True
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1")[0], 503)

    def test_a_sale_with_no_medicine_reads_no_patient_and_writes_nothing(self):
        self.assertEqual(self.sell(("BREAD", "Food", 2)), (200, {"verdict": "allow"}))
        kinds = {c[1] for c in self.shop.calls if c[0] == "list"}
        self.assertFalse(kinds & {f"{P} Prescription", "Customer", f"{P} Pharmacist"})
        self.assertFalse([c for c in self.shop.calls if c[0] == "insert"])


class Dispensing(Base):
    def test_an_allowed_prescription_reserves_the_patients_next_number(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21, fills=2)
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1"), (200, {"verdict": "allow"}))
        (d,) = self.shop.dispensings()
        self.assertEqual((d["name"], d["status"], d["sale_ref"], d["prescription"], d["pos_opening"], d["day"]),
                         (f"{RX.patient_key('Ann')}~0001", "Reserved", "sale-1", "RX1", "DAY-1", "2026-10-22"))
        self.assertEqual(json.loads(d["lines_json"])["lines"][0]["qty"], 21)

    def test_pay_pressed_again_keeps_the_same_reservation(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.sell(("AMOX", "Rx", 21), rx="RX1")
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1"), (200, {"verdict": "allow"}))
        self.assertEqual([(d["name"], d["status"]) for d in self.shop.dispensings()], [(f"{RX.patient_key('Ann')}~0001", "Reserved")])

    def test_a_changed_basket_replaces_and_releases_its_earlier_reservation(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.sell(("AMOX", "Rx", 21), rx="RX1")
        self.sell(("AMOX", "Rx", 14), rx="RX1")
        k = RX.patient_key("Ann")
        self.assertEqual([(d["name"], d["status"]) for d in self.shop.dispensings()],
                         [(f"{k}~0001", "Released"), (f"{k}~0002", "Reserved")])

    def test_the_medicine_taken_off_releases_the_reservation(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.sell(("AMOX", "Rx", 21), rx="RX1")
        self.assertEqual(self.sell(("BREAD", "Food", 1)), (200, {"verdict": "allow"}))
        self.assertEqual(self.shop.dispensings()[0]["status"], "Released")

    def test_another_sale_cannot_take_a_reserved_fill(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-x")
        code, out = self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-y")
        self.assertIn("is held by an unpaid sale", out["reason"])

    def test_a_booked_sale_reads_dispensed_and_its_status_is_written_back(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21, fills=2)
        self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="Sale-X")
        self.shop.booked("Sale-X")
        self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-y")
        self.assertEqual([d["status"] for d in self.shop.dispensings()], ["Dispensed", "Reserved"])

    def test_an_unbooked_sale_releases_its_fill_only_when_its_day_closes(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-x", opening="DAY-1")
        self.shop.add("POS Opening Entry", name="DAY-1", status="Open")
        self.assertIn("held by an unpaid sale", self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-y", opening="DAY-2")[1]["reason"])
        self.shop.rows("POS Opening Entry")[0]["status"] = "Closed"
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-z", opening="DAY-2")[1], {"verdict": "allow"})
        self.assertEqual(self.shop.dispensings()[0]["status"], "Released")

    def test_two_tills_one_fill_one_insert_wins_and_the_other_decides_again(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)

        def other_till(doc):          # the other till takes Ann's next number between our read and our insert
            self.shop.rows(f"{P} Dispensing").append(dict(doc, name=doc["key"], sale_ref="sale-other",
                                                           lines_json=doc["lines_json"]))
        self.shop.before_insert = other_till
        code, out = self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-mine")
        self.assertIn("is held by an unpaid sale", out["reason"])
        self.assertEqual(len(self.shop.dispensings()), 1)

    def test_two_tills_at_once_on_real_threads(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        outs = []
        barrier = threading.Barrier(2)

        def till(ref):
            barrier.wait()
            outs.append(self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref=ref)[1]["verdict"])
        ts = [threading.Thread(target=till, args=(f"sale-{i}",)) for i in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(sorted(outs), ["allow", "refuse"])
        self.assertEqual([d["status"] for d in self.shop.dispensings()], ["Reserved"])

    def test_a_return_of_returnable_medicine_records_a_give_back_that_counts_once_booked(self):
        self.shop.add(f"{P} Dispensing", name="Ann~0001", key="Ann~0001", seq=1, customer="Ann", status="Dispensed",
                      source="till", sale_ref="sale-0", day="2026-10-21",
                      lines_json=json.dumps({"lines": [{"item": "PARA", "qty": 2, "rx": "", "schedules": ["PMED"]}]}))
        self.shop.booked("sale-0", name="INV-0")
        code, out = self.sell(("PARA", "OTC", -2), stage="return", sale_ref="ret-key-1", return_of="INV-0")
        self.assertEqual(out, {"verdict": "allow"})
        give = self.shop.dispensings()[1]
        self.assertEqual((give["status"], give["give_back"], json.loads(give["lines_json"])["lines"][0]["qty"]),
                         ("Reserved", 1, -2))

    def test_a_dispensed_return_is_refused_at_the_till(self):
        code, out = self.sell(("AMOX", "Rx", -21), stage="return", sale_ref="ret-key", return_of="INV-0")
        self.assertEqual(out["reason"], "Line 1: AMOX: Dispensed medicine cannot be taken back.")


class SentSale(Base):
    """0.1.5 (BUG-PH-001): the pharmacist rings a prescription, presses Pay (the check reserves the fill) and sends the sale
    to the dispensary's cash till; a counter assistant who is not a pharmacist rings it up there and takes the money."""

    def setUp(self):
        super().setUp()
        self.shop.prescription("RX1", "Ann", "AMOX", 21)            # one fill
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="Sale-PH")[1], {"verdict": "allow"})

    def pay(self, qty=21, operator="cash@shop", sale_ref="sale-cash"):
        return self.sell(("AMOX", "Rx", qty), rx="RX1", sale_ref=sale_ref, operator=operator, opening="DAY-CASH")[1]

    def test_the_cashier_pays_it_in_one_press_and_the_dispensing_names_both(self):
        self.shop.sent()
        self.assertEqual(self.pay(), {"verdict": "allow"})
        old, new = self.shop.dispensings()
        self.assertEqual(old["status"], "Released")                 # the pharmacist's reservation, taken over
        self.assertEqual((new["status"], new["sale_ref"], new["operator"], new["pharmacist_name"], new["park"],
                          new["pos_opening"]),
                         ("Reserved", "sale-cash", "cash@shop", "P. Pharmacist", "PARK-1", "DAY-CASH"))
        self.shop.booked("sale-cash")                               # paid: the till deletes the park as it books
        self.shop.gone("PARK-1", "PARK-1-DRAFT")
        self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-next")
        self.assertEqual([d["status"] for d in self.shop.dispensings()], ["Released", "Dispensed"])

    def test_pay_pressed_again_keeps_the_taken_over_reservation(self):
        self.shop.sent()
        self.pay()
        self.assertEqual(self.pay(), {"verdict": "allow"})
        self.assertEqual([d["status"] for d in self.shop.dispensings()], ["Released", "Reserved"])

    def test_more_than_the_pharmacist_sent_is_refused_with_the_way_back(self):
        self.shop.prescription("RX2", "Ann", "AMOX", 42)
        self.shop.sent()
        out = self.sell(("AMOX", "Rx", 42), rx="RX2", sale_ref="sale-cash", operator="cash@shop")[1]
        self.assertEqual(out["reason"], "Line 1: AMOX: Only a pharmacist may sell this: it is more than the pharmacist "
                                        "sent. Send it back to their till.")
        self.assertEqual([d["status"] for d in self.shop.dispensings()], ["Reserved"])   # refused: nothing taken over

    def test_a_park_another_cashier_rang_up_is_not_this_sale(self):
        self.shop.sent(rung_by="other@shop")
        out = self.pay()
        self.assertEqual(out["reason"], "Line 1: AMOX: Only a pharmacist may sell this. Ask a pharmacist to ring it up; "
                                        "they can send it to this till.")

    def test_a_park_nobody_rang_up_yet_is_not_this_sale(self):
        self.shop.sent(rung=False)
        self.assertIn("Ask a pharmacist to ring it up", self.pay()["reason"])

    def test_a_park_sent_by_someone_who_is_not_a_pharmacist_today_is_refused(self):
        self.shop.sent(owner="old@shop")                            # their licence ran out yesterday
        self.assertIn("the one who sent it can't today. Ask a pharmacist to take payment.", self.pay()["reason"])
        self.shop.gone("PARK-1", "PARK-1-DRAFT")
        self.shop.sent(owner="nobody@shop")                         # not on the Pharmacist list at all
        self.assertIn("the one who sent it can't today", self.pay()["reason"])

    def test_a_park_for_another_customer_is_not_this_sale(self):
        self.shop.sent(customer="Bob")
        self.assertIn("Ask a pharmacist to ring it up", self.pay()["reason"])

    def test_voided_at_the_cash_till_its_fill_comes_back(self):
        self.shop.sent()
        self.pay()
        self.shop.gone("PARK-1", "PARK-1-DRAFT")                    # the cashier voids it: the park and its draft go
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-again")[1], {"verdict": "allow"})
        self.assertEqual([d["status"] for d in self.shop.dispensings()], ["Released", "Released", "Reserved"])

    def test_still_parked_its_fill_stays_held(self):
        self.shop.sent()
        self.pay()
        out = self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-again")[1]
        self.assertIn("is held by an unpaid sale", out["reason"])

    def test_a_park_the_shop_will_not_show_is_never_read_as_gone(self):
        self.shop.sent()
        self.pay()
        self.shop.gone("PARK-1", "PARK-1-DRAFT")
        real = self.shop.get_one

        def hidden(url, key, doctype, name):
            if doctype == "POS Invoice":
                raise app.ShopUnreadable("the shop answered 403")
            return real(url, key, doctype, name)
        self.shop.get_one = hidden
        self.assertIn("is held by an unpaid sale", self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-again")[1]["reason"])

    def test_the_park_is_read_before_the_sale(self):
        self.shop.sent()
        self.pay()
        self.shop.calls.clear()
        self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-again")
        reads = [c for c in self.shop.calls if c[0] == "list" and c[1] == "POS Invoice"]
        park = next(i for i, c in enumerate(reads) if c[2] == [["name", "in", ["PARK-1"]]])
        sale = next(i for i, c in enumerate(reads) if "custom_mpos_sale_ref" in c[3] and "docstatus" in c[3]
                    and any(f[0] == "custom_mpos_sale_ref" for f in c[2]))
        self.assertLess(park, sale)

    def test_a_sent_sale_is_paid_once_a_fresh_basket_is_not_the_sent_sale(self):
        self.shop.sent()
        self.assertEqual(self.pay(), {"verdict": "allow"})          # rung up from the park and paid (not booked yet)
        # the cashier clears that basket and rings the line again: the park is taken, so this is the cashier's own sale
        self.assertIn("Ask a pharmacist to ring it up", self.pay(sale_ref="sale-cash-2")["reason"])

    def test_a_shop_on_0_1_4_offers_no_sent_sale(self):
        real = self.shop.get_list

        def old_shop(url, key, doctype, fields, filters=None, *a, **k):
            if doctype == f"{P} Dispensing" and ("park" in fields or any(f[0] == "park" for f in filters or [])):
                raise app.ShopUnreadable("the shop answered 417")
            return real(url, key, doctype, fields, filters, *a, **k)
        self.shop.get_list = old_shop
        self.shop.sent()
        self.assertIn("Ask a pharmacist to ring it up", self.pay()["reason"])

    def test_a_shop_still_on_0_1_4_is_read_without_the_park(self):
        real = self.shop.get_list

        def old_shop(url, key, doctype, fields, *a, **k):
            if doctype == f"{P} Dispensing" and "park" in fields:
                raise app.ShopUnreadable("the shop answered 417")
            return real(url, key, doctype, fields, *a, **k)
        self.shop.get_list = old_shop
        self.shop.prescription("RX2", "Ann", "AMOX", 21, fills=2)
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX2", sale_ref="sale-2")[1], {"verdict": "allow"})


class SentWalkIn(Base):
    def test_a_walk_in_sale_with_a_pharmacist_only_line_sent_to_the_cash_till(self):
        self.shop.add(f"{P} Drug Schedule", name="P1", axis="Pharmacy", pharmacist_only=1, returnable=1)
        self.shop.add(f"{P} Item Schedule", parent="PARA", schedule="P1", effective_from=None)
        self.shop.sent(park="PARK-W", sale_ref="walk-ph", customer="Cash Sale", items=(("PARA", 1),))
        out = self.sell(("PARA", "OTC", 1), customer="Cash Sale", sale_ref="walk-cash", operator="cash@shop")[1]
        self.assertEqual(out, {"verdict": "allow"})
        (d,) = self.shop.dispensings()                             # recorded, so the park is paid once
        self.assertEqual((d["customer"], d["park"], d["operator"], d["pharmacist_name"]),
                         ("Cash Sale", "PARK-W", "cash@shop", "P. Pharmacist"))
        self.assertIn("Ask a pharmacist", self.sell(("PARA", "OTC", 1), customer="Cash Sale", sale_ref="w2",
                                                     operator="other@shop")[1]["reason"])
        self.assertIn("Ask a pharmacist", self.sell(("PARA", "OTC", 1), customer="Cash Sale", sale_ref="w3",
                                                     operator="cash@shop")[1]["reason"])   # a fresh basket: not sent


class People(Base):
    def test_an_operator_with_no_pharmacist_record_is_stopped(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        out = self.sell(("AMOX", "Rx", 21), rx="RX1", operator="assistant@shop")[1]
        self.assertIn("Only a pharmacist may sell this", out["reason"])
        self.assertFalse(self.shop.dispensings())

    def test_a_lapsed_licence_is_refused(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.assertIn("ran out on 2026-10-21", self.sell(("AMOX", "Rx", 21), rx="RX1", operator="old@shop")[1]["reason"])

    def test_the_profiles_own_default_customer_is_a_walk_in(self):
        self.shop.prescription("RX1", "Walk-in", "AMOX", 21)
        self.shop.add("Customer", name="Walk-in")
        self.assertIn("walk-in", self.sell(("AMOX", "Rx", 21), rx="RX1", customer="Walk-in")[1]["reason"])

    def test_another_profiles_default_customer_is_a_walk_in_on_the_desk_too(self):
        self.shop.add("POS Profile", name="Front", customer="Front Walk-in")
        self.shop.add("Customer", name="Front Walk-in")
        self.shop.prescription("RX1", "Front Walk-in", "AMOX", 21)
        out = self.call("/rxc/desk/invoice", desk_body("Sales Invoice", "SI-1", [{"item_code": "AMOX", "item_group": "Rx",
                                                                                  "stock_qty": 21000}], customer="Front Walk-in",
                                                       rx="RX1"))[1]
        self.assertIn("walk-in", out["reason"])

    def test_the_identity_values_never_leave_the_shop_only_whether_they_are_set(self):
        self.shop.prescription("RX1", "Ann", "TRAM", 10)
        self.assertEqual(self.sell(("TRAM", "CD", 10), rx="RX1")[1], {"verdict": "allow"})
        reads = [c for c in self.shop.calls if c[0] == "list" and c[1] == f"{P} Patient"]
        self.assertTrue(reads)
        self.assertTrue(all(fields == ["name", "customer"] for *_x, fields in reads))   # never a value, only whose record
        self.assertIn([["customer", "=", "Ann"], ["id_number", "is", "set"]], [c[2] for c in reads])
        # 0.1.2: nothing about the patient is asked of Customer but that the customer exists
        self.assertEqual([c[2] for c in self.shop.calls if c[0] == "list" and c[1] == "Customer"], [[["name", "=", "Ann"]]])

    def test_a_schedule_that_needs_consent_reads_only_whether_the_patients_consent_date_has_come(self):
        sched = next(r for r in self.shop.rows(f"{P} Drug Schedule") if r["name"] == "POM")
        sched["needs_consent"] = 1
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.assertIn("consent to keep their records", self.sell(("AMOX", "Rx", 21), rx="RX1")[1]["reason"])
        reads = [c for c in self.shop.calls if c[0] == "list" and c[1] == f"{P} Patient"]
        self.assertTrue(all(fields == ["name", "customer"] for *_x, fields in reads))   # the date never leaves the shop
        ann = next(r for r in self.shop.rows(f"{P} Patient") if r["customer"] == "Ann")
        ann["consent_date"] = "2026-11-01"                                       # dated ahead: a mis-keyed consent
        self.assertIn("consent to keep their records", self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-2")[1]["reason"])
        self.assertIn(["consent_date", "<=", "2026-10-22"], [c[2][1] for c in self.shop.calls
                                                             if c[0] == "list" and c[1] == f"{P} Patient" and len(c[2]) > 1])
        ann["consent_date"] = "2026-10-01"
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-3")[1], {"verdict": "allow"})

    def test_a_shop_that_drops_a_filter_on_a_patient_field_is_unreadable_never_a_field_filled_in(self):
        # a field the service's user may not read, its filter dropped by the shop: the record would answer "set" both ways
        real = self.shop._match
        self.shop._match = lambda r, filters: real(r, [x for x in filters or [] if x[0] not in ("id_number", "birth_date")])
        self.shop.add(f"{P} Patient", name="f6e5d4c3b2", customer="Bob", id_number="", birth_date="", authority="")
        self.shop.prescription("RX1", "Bob", "TRAM", 10)
        self.assertEqual(self.sell(("TRAM", "CD", 10), rx="RX1", customer="Bob")[0], 503)

    def test_a_shop_that_answers_a_field_for_a_patient_record_it_does_not_list_is_unreadable(self):
        # the shop lists no patient record for Bob, yet answers a field of one: never trusted
        self.shop.add(f"{P} Patient", name="f6e5d4c3b2", customer="Bob", id_number="", birth_date="", authority="")
        real = self.shop._match
        self.shop._match = lambda r, filters: False if filters == [["customer", "=", "Bob"]] else real(r, filters)
        self.shop.prescription("RX1", "Bob", "TRAM", 10)
        self.assertEqual(self.sell(("TRAM", "CD", 10), rx="RX1", customer="Bob")[0], 503)

    def test_an_answer_about_another_customers_patient_record_is_unreadable(self):
        # a shop that drops only the customer filter, where every patient's ID is set: never read as this patient's
        real = self.shop._match
        self.shop._match = lambda r, filters: real(r, [x for x in filters or [] if x[0] != "customer"])
        self.shop.prescription("RX1", "Bob", "TRAM", 10)
        self.assertEqual(self.sell(("TRAM", "CD", 10), rx="RX1", customer="Bob")[0], 503)

    def test_a_customer_with_no_patient_record_has_nothing_on_record(self):
        self.shop.prescription("RX1", "Bob", "TRAM", 10)
        self.assertFalse([r for r in self.shop.rows(f"{P} Patient") if r["customer"] == "Bob"])
        self.assertIn("national or residence ID", self.sell(("TRAM", "CD", 10), rx="RX1", customer="Bob")[1]["reason"])
        self.shop.add(f"{P} Patient", name="f6e5d4c3b2", customer="Bob", id_number="ID-2", birth_date="1990-02-02")
        self.assertEqual(self.sell(("TRAM", "CD", 10), rx="RX1", customer="Bob", sale_ref="sale-2")[1], {"verdict": "allow"})

    def test_the_settings_walk_in_list_counts_too(self):
        self.assertIn("walk-in", self.sell(("AMOX", "Rx", 21), rx="RX1", customer="Cash Sale")[1]["reason"])

    def test_a_controlled_sale_needs_the_customers_id(self):
        self.shop.prescription("RX1", "Bob", "TRAM", 10)
        self.assertIn("national or residence ID", self.sell(("TRAM", "CD", 10), rx="RX1", customer="Bob")[1]["reason"])

    def test_a_strip_counts_seven_against_the_prescription(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 14)
        body = till_body([("AMOX", "Rx", 3)], rx="RX1")
        body["context"]["lines"][0]["uom"] = "Strip"
        self.assertIn("has only 14", self.call("/rxc/dispensary", body)[1]["reason"])

    def test_the_front_sends_prescription_medicine_to_the_dispensary(self):
        self.assertIn("Sell this at the dispensary", self.sell(("AMOX", "Rx", 21), route="/rxc/front")[1]["reason"])
        self.assertEqual(self.sell(("PARA", "OTC", 2), route="/rxc/front")[1], {"verdict": "allow"})


class Register(Base):
    """0.1.3: what the prescriptions register reads, written on the dispensing the service reserves (K1-c)."""
    def test_the_reserved_dispensing_keeps_the_prescriber_the_dose_and_the_pharmacists_name(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21, directions="1 capsule three times a day")
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1")[1], {"verdict": "allow"})
        (d,) = self.shop.dispensings()
        self.assertEqual((d["prescriber"], d["directions"], d["pharmacist_name"]),
                         ("Dr Who", "AMOX: 1 capsule three times a day", "P. Pharmacist"))

    def test_only_a_licensed_pharmacist_is_named_never_a_delegate(self):
        self.shop.add(f"{P} Pharmacist", name="tech@shop", user="tech@shop", full_name="T. Technician", active=1,
                      valid_until="2027-10-22", delegate=1)
        self.shop.add(f"{P} Drug Schedule", name="RXONLY", axis="Prescription only", needs_prescription=1, returnable=0,
                      return_gives_back=1)
        self.shop.add("Item", name="CREAM", stock_uom="Nos", variant_of=None, pp_rxc_directions="apply twice a day")
        self.shop.add(f"{P} Item Schedule", parent="CREAM", schedule="RXONLY", effective_from=None)
        self.shop.prescription("RX5", "Ann", "CREAM", 1)
        self.assertEqual(self.sell(("CREAM", "Food", 1), rx="RX5", operator="tech@shop")[1], {"verdict": "allow"})
        (d,) = self.shop.dispensings()
        self.assertEqual(d["pharmacist_name"], "")

    def test_a_0_1_2_shop_is_answered_as_before(self):
        # the 0.1.3 service may move first: a shop that refuses the new tick is asked again without it, and a Desk
        # subscription that does not send the date is answered allow, never fill
        real = self.shop.get_list

        def old_shop(url, key, doctype, fields, *a, **k):
            if "register_books_rx_date" in fields:
                raise app.ShopUnreadable("the shop answered 417")
            return real(url, key, doctype, fields, *a, **k)
        self.shop.get_list = old_shop
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        body = desk_body("Sales Invoice", "SI-1", [{"item_code": "AMOX", "item_group": "Rx", "stock_qty": 21000}], rx="RX1")
        del body["context"]["fields"]["pp_rxc_rx_date"]
        self.assertEqual(self.call("/rxc/desk/invoice", body), (200, {"verdict": "allow"}))
        self.shop.get_list = real

    def test_a_shop_that_refuses_the_key_is_not_asked_again_without_the_tick(self):
        asked = []

        def refused(url, key, doctype, fields, *a, **k):
            asked.append(doctype)
            raise app.ShopUnreadable("the shop answered 401")
        self.shop.get_list = refused
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1")[0], 503)
        self.assertLessEqual(asked.count(f"{P} Drug Schedule"), 1)

    def test_the_schedule_tick_is_read_and_the_till_asks_for_the_date(self):
        self.shop.add(f"{P} Drug Schedule", name="DATED", axis="Register", needs_prescription=1, pharmacist_only=1,
                      register_books_rx_date=1, returnable=0, return_gives_back=1)
        self.shop.add("Item", name="MORPH", stock_uom="Nos", variant_of=None, pp_rxc_directions="")
        self.shop.add(f"{P} Item Schedule", parent="MORPH", schedule="DATED", effective_from=None)
        self.shop.prescription("RX9", "Ann", "MORPH", 5, written="2026-10-21")
        out = self.sell(("MORPH", "CD", 5), rx="RX9")[1]
        self.assertIn("needs the prescription's date in Sale details: 2026-10-21.", out["reason"])
        out = self.sell(("MORPH", "CD", 5), rx="RX9", details={"Rx Date": "2026-10-21"})[1]
        self.assertEqual(out, {"verdict": "allow"})


class TillFill(Base):
    """0.1.4: the dispensary's check at its filling address answers with the prescription's date (``PB-27``)."""
    def setUp(self):
        super().setUp()
        self.shop.prescription("RX1", "Ann", "AMOX", 21, fills=2, written="2026-10-19")

    def test_the_filling_address_fills_the_date_and_the_second_call_is_answered_the_same(self):
        first = self.sell(("AMOX", "Rx", 21), rx="RX1", route="/rxc/dispensary/fill")
        self.assertEqual(first, (200, {"verdict": "allow", "fill": {f"{P} Rx Date": "2026-10-19"}}))
        # the till writes it, prices the sale again and asks once more on the filled sale: the same value, one reservation
        again = self.sell(("AMOX", "Rx", 21), rx="RX1", route="/rxc/dispensary/fill", details={"Rx Date": "2026-10-19"})
        self.assertEqual(again, first)
        (d,) = self.shop.dispensings()
        self.assertEqual(d["status"], RX.RESERVED)

    def test_the_old_address_never_fills_so_a_shop_still_on_0_1_3_is_answered_as_before(self):
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1"), (200, {"verdict": "allow"}))
        out = self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-2", details={"Rx Date": "2026-10-01"})[1]
        self.assertIn("was written on 2026-10-19. Correct the date in Sale details.", out["reason"])

    def test_a_return_is_never_filled_and_the_front_has_no_filling_address(self):
        # a return without its sale may carry a line being sold (an exchange on the selling screen): never filled there
        body = till_body([("AMOX", "Rx", 21)], rx="RX1", stage="return")
        self.assertEqual(self.call("/rxc/dispensary/fill", body)[1], {"verdict": "allow"})
        self.assertEqual(self.svc.handle("POST", "/rxc/front/fill", {}, b"{}")[0], 404)


def press_body(name, user="officer@shop", reference=None, doctype=f"{P} Erasure"):
    inputs = {"reference": reference} if reference is not None else {}
    return {"point": "desk_action/1", "context": {"v": 1, "action": "a1", "idempotency_key": "k1", "label": "x",
            "lang": "en", "inputs": inputs, "user": user,
            "records": [{"doctype": doctype, "name": name, "fields": {"name": name}}]}}


class Erasure(Base):
    """0.1.4 (R-16): after the keeping period the Records Officer lists the patients due and erases them; never a timer."""
    ERA = "RXC-ERA-00001"

    def setUp(self):
        super().setUp()
        self.svc = app.Service(dict(CONF, IVN_SECRET_LIST_DUE="secret-list_due", IVN_SECRET_ERASE="secret-erase"),
                               api=self.shop, now=lambda: NOW)
        self.shop.rows(f"{P} Settings")[0]["keep_years"] = 2          # today 2026-10-22: due if nothing since 2024-10-22
        self.shop.add(f"{P} Erasure", name=self.ERA, status="Draft")
        for c in ("Old", "Mixed", "OnlyPatient", "Moved"):
            self.shop.add("Customer", name=c)
        for c, day, written in (("Old", "2023-05-01", "2023-04-30"), ("Mixed", "2023-01-01", "2025-06-01"),
                                ("Moved", "2023-02-01", "2023-02-01")):
            self.shop.add(f"{P} Prescription", name=f"RX-{c}", customer=c, date_written=written)
            self.shop.add(f"{P} Dispensing", name=f"{c}~0001", key=f"{c}~0001", customer=c, day=day, seq=1,
                          status="Dispensed", lines_json="{}")
        self.shop.add(f"{P} Patient", name="p-old", customer="Old", creation="2023-04-01 10:00:00",
                      modified="2023-04-01 10:00:00")
        self.shop.add(f"{P} Patient", name="p-only", customer="OnlyPatient", creation="2022-01-05 09:00:00",
                      modified="2022-01-05 09:00:00")
        self.shop.rows("Customer")[-1]["pp_rxc_id_number"] = "ID-9"      # Moved still holds 0.1.1's ID on the customer
        self.shop.prescription("RX1", "Ann", "AMOX", 21, written="2026-10-19")

    def press(self, route, body, secret=None):
        raw = json.dumps(body).encode()
        return self.svc.handle("POST", route, sign(raw, secret or f"secret-{app.PRESSES[route]}"), raw)

    def record(self):
        return next(r for r in self.shop.rows(f"{P} Erasure") if r["name"] == self.ERA)

    def listed(self):
        return self.press("/rxc/erasure/list", press_body(self.ERA))

    def test_nobody_is_listed_until_the_shop_sets_its_period(self):
        del self.shop.rows(f"{P} Settings")[0]["keep_years"]
        code, out = self.listed()
        self.assertEqual((code, out["message"]["level"]), (200, "warning"))
        self.assertIn("Keep a patient's records for (years)", out["message"]["body"])
        self.assertEqual(self.record()["status"], "Draft")

    def test_the_list_holds_each_patient_whose_newest_record_of_every_kind_is_older_than_the_period(self):
        code, out = self.listed()
        self.assertEqual(code, 200)
        self.assertIn("3 patients with no record since 2024-10-22", out["message"]["body"])
        rec = self.record()
        self.assertEqual((rec["status"], rec["keep_years"], rec["cut_off"]), ("Listed", 2, "2024-10-22"))
        # Mixed's prescription of 2025 keeps them; Ann buys today; Moved is listed (the act keeps them, below)
        self.assertEqual([(r["customer"], r["last_record"], r["prescriptions"], r["dispensings"]) for r in rec["patients"]],
                         [("OnlyPatient", "2022-01-05", 0, 0), ("Moved", "2023-02-01", 1, 1), ("Old", "2023-05-01", 1, 1)])

    def test_erase_deletes_the_dispensings_then_the_prescriptions_then_the_patient_and_keeps_the_record(self):
        self.listed()
        code, out = self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes 12/2026"))
        self.assertEqual(code, 200)
        self.assertEqual(out["message"]["body"], "Erased 2 patients. 1 kept: each row says why. This erasure is done. "
                                                 + RX.COPIES_KEPT)
        old = [x for x in self.shop.deleted if x[1] in ("Old~0001", "RX-Old", "p-old")]     # rows run side by side
        self.assertEqual(old, [(f"{P} Dispensing", "Old~0001"), (f"{P} Prescription", "RX-Old"), (f"{P} Patient", "p-old")])
        self.assertIn((f"{P} Patient", "p-only"), self.shop.deleted)
        # 0.1.1's Customer fields are asked set or not: their values never leave the shop
        reads = [c for c in self.shop.calls if c[0] == "list" and c[1] == "Customer"]
        self.assertTrue(reads and all(c[3] == ["name"] for c in reads))
        rec = self.record()
        self.assertEqual((rec["status"], rec["erased_by"], rec["reference"], rec["erased_count"], rec["kept_count"]),
                         ("Erased", "officer@shop", "Minutes 12/2026", 2, 1))
        self.assertEqual({r["customer"]: r["outcome"] for r in rec["patients"]},
                         {"OnlyPatient": "Erased", "Old": "Erased", "Moved": RX.KEPT_MOVED})
        self.assertTrue(self.shop.rows(f"{P} Dispensing"))           # Ann's, Mixed's and Moved's are untouched
        self.assertEqual(self.press("/rxc/erasure/erase", press_body(self.ERA, reference="x"))[1]["message"]["body"],
                         "This erasure is done.")

    def test_a_begun_erasure_is_never_listed_again_its_rows_are_the_record(self):
        self.listed()
        t = iter([0.0, 0.0] + [100.0] * 50)        # the press starts; the first patient begins; the rest run out of time
        self.svc.clock = lambda: next(t)
        self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))
        self.assertTrue(any(r["outcome"] for r in self.record()["patients"]))
        before = [dict(r) for r in self.record()["patients"]]
        out = self.listed()[1]
        self.assertIn("This erasure has begun", out["message"]["body"])
        self.assertEqual(self.record()["patients"], before)

    def test_a_patient_record_changed_since_the_cut_off_keeps_the_patient(self):
        next(r for r in self.shop.rows(f"{P} Patient") if r["name"] == "p-only")["modified"] = "2026-10-01 09:00:00"
        self.listed()
        self.assertNotIn("OnlyPatient", [r["customer"] for r in self.record()["patients"]])

    def test_a_patient_who_came_back_since_the_list_is_kept(self):
        self.listed()
        self.shop.add(f"{P} Dispensing", name="Old~0002", key="Old~0002", customer="Old", day="2026-10-20", seq=2,
                      status="Dispensed", lines_json="{}")
        self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))
        rows = {r["customer"]: r["outcome"] for r in self.record()["patients"]}
        self.assertEqual(rows["Old"], "Kept: a record dated 2026-10-20 is inside the period")
        self.assertTrue([r for r in self.shop.rows(f"{P} Patient") if r["customer"] == "Old"])

    def test_a_period_lengthened_after_the_list_keeps_everyone_it_now_covers(self):
        self.listed()
        self.shop.rows(f"{P} Settings")[0]["keep_years"] = 5           # the shop read its law again: 5 years
        self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))
        self.assertFalse(getattr(self.shop, "deleted", []))
        self.assertTrue(all(r["outcome"].startswith("Kept") for r in self.record()["patients"]))

    def test_a_shop_that_answers_for_another_customer_erases_nothing(self):
        self.listed()
        real = self.shop.get_list

        def dropped(url, key, doctype, fields, filters=None, *a, **k):   # the customer filter dropped on the patient's reads
            if doctype == f"{P} Dispensing" and filters == [["customer", "=", "Old"]]:
                filters = None
            return real(url, key, doctype, fields, filters, *a, **k)
        self.shop.get_list = dropped
        out = self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))[1]
        self.assertFalse([x for x in getattr(self.shop, "deleted", []) if x[0] == f"{P} Dispensing"])
        self.assertEqual(out["message"]["level"], "warning")

    def test_a_done_erasure_is_never_listed_again(self):
        self.listed()
        self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))
        self.assertEqual(self.record()["status"], "Erased")
        self.assertIn("This erasure is done", self.listed()[1]["message"]["body"])

    def test_erase_needs_the_list_and_a_destruction_record(self):
        out = self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))[1]
        self.assertEqual(out["message"]["body"], "List the patients due first.")
        self.listed()
        out = self.press("/rxc/erasure/erase", press_body(self.ERA, reference="  "))[1]
        self.assertIn("Type your destruction record", out["message"]["body"])
        self.assertFalse(getattr(self.shop, "deleted", []))

    def test_a_long_erasure_stops_in_time_and_the_next_press_goes_on(self):
        self.listed()
        t = iter([0.0] + [100.0] * 50)              # the press started at 0; every row's check reads 100 s later
        self.svc.clock = lambda: next(t)
        out = self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))[1]
        self.assertIn("3 still to do: press Erase these patients again.", out["message"]["body"])
        self.assertEqual(self.record()["status"], "Listed")
        self.svc.clock = lambda: 0.0
        self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))
        self.assertEqual(self.record()["status"], "Erased")

    def test_a_shop_that_refuses_a_delete_stops_the_act_and_says_so(self):
        self.listed()
        def refuse(*a):
            raise app.ShopUnreadable("the shop answered 417")
        self.shop.delete = refuse
        out = self.press("/rxc/erasure/erase", press_body(self.ERA, reference="Minutes"))[1]
        self.assertEqual(out["message"]["level"], "warning")
        self.assertIn("press Erase again", out["message"]["body"])
        self.assertEqual(self.record()["status"], "Listed")

    def test_each_button_takes_only_its_own_secret_and_one_shop_without_it_refuses(self):
        body = press_body(self.ERA, reference="Minutes")
        self.assertEqual(self.press("/rxc/erasure/erase", body, secret="secret-list_due")[0], 401)
        self.assertEqual(self.press("/rxc/erasure/erase", body, secret="secret-dispensary")[0], 401)
        plain = app.Service(CONF, api=self.shop, now=lambda: NOW)          # a 0.1.3 shop's settings: no button secrets
        raw = json.dumps(body).encode()
        self.assertEqual(plain.handle("POST", "/rxc/erasure/erase", sign(raw, "secret-erase"), raw)[0], 401)
        self.assertEqual(self.press("/rxc/erasure/list", press_body(self.ERA, doctype="Customer"))[0], 400)
        self.assertFalse(getattr(self.shop, "deleted", []))


class Desk(Base):
    def item(self, code="AMOX", group="Rx", qty=21, **parents):
        return dict({"item_code": code, "item_group": group, "stock_qty": int(qty * 1000)}, **parents)

    def test_an_invoice_with_no_prescription_number_is_refused(self):
        out = self.call("/rxc/desk/invoice", desk_body("Sales Invoice", "SI-1", [self.item()]))[1]
        self.assertIn("Add a prescription number field", out["reason"])

    def test_the_chain_spends_one_fill(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.assertEqual(self.call("/rxc/desk/order", desk_body("Sales Order", "SO-1", [self.item()], rx="RX1"))[1],
                         FILLED)
        self.shop.add("Sales Order", name="SO-1", docstatus=1)
        dn = desk_body("Delivery Note", "DN-1", [self.item(against_sales_order="SO-1", so_detail="r1")], rx="RX1", user="clerk@shop")
        self.assertEqual(self.call("/rxc/desk/delivery", dn)[1], FILLED)     # 0.1.3: the date filled on each document
        si = desk_body("Sales Invoice", "SI-1", [self.item(sales_order="SO-1", so_detail="r1", delivery_note="DN-1",
                                                          dn_detail="r2")], rx="RX1",
                       user="clerk@shop")
        self.assertEqual(self.call("/rxc/desk/invoice", si)[1], FILLED)
        (d,) = self.shop.dispensings()
        self.assertEqual((d["source"], d["document_type"], d["document"]), ("desk", "Sales Order", "SO-1"))
        again = desk_body("Sales Invoice", "SI-2", [self.item()], rx="RX1")
        self.assertIn("nothing left", self.call("/rxc/desk/invoice", again)[1]["reason"])

    def test_a_parents_name_alone_never_skips_the_check(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        dn = desk_body("Delivery Note", "DN-9", [self.item(against_sales_order="SO-1")], user="clerk@shop")
        self.assertIn("Only a pharmacist", self.call("/rxc/desk/delivery", dn)[1]["reason"])

    def test_a_document_the_shop_will_not_show_keeps_its_fill(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.call("/rxc/desk/order", desk_body("Sales Order", "SO-1", [self.item()], rx="RX1"))
        real_one = self.shop.get_one

        def hidden(url, key, doctype, name):        # a User Permission hides the order from the app's user
            if doctype == "Sales Order":
                raise app.ShopUnreadable("the shop answered 403")
            return real_one(url, key, doctype, name)
        self.shop.get_one = hidden
        out = self.call("/rxc/desk/invoice", desk_body("Sales Invoice", "SI-2", [self.item()], rx="RX1"))[1]
        self.assertIn("nothing left", out["reason"])

    def test_a_reservation_is_never_made_after_the_tills_budget(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        ticks = iter([0.0] + [9.0] * 50)
        self.svc.clock = lambda: next(ticks)
        self.assertEqual(self.sell(("AMOX", "Rx", 21), rx="RX1")[0], 503)
        self.assertFalse(self.shop.dispensings())

    def test_a_cancelled_order_gives_its_fill_back(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        self.call("/rxc/desk/order", desk_body("Sales Order", "SO-1", [self.item()], rx="RX1"))
        self.shop.add("Sales Order", name="SO-1", docstatus=2)
        out = self.call("/rxc/desk/invoice", desk_body("Sales Invoice", "SI-2", [self.item()], rx="RX1"))[1]
        self.assertEqual(out, FILLED)
        self.assertEqual(self.shop.dispensings()[0]["status"], "Released")

    def test_a_clerk_cannot_begin_a_chain_of_pharmacist_only_medicine(self):
        self.shop.prescription("RX1", "Ann", "AMOX", 21)
        out = self.call("/rxc/desk/order", desk_body("Sales Order", "SO-1", [self.item()], rx="RX1", user="clerk@shop"))[1]
        self.assertIn("Only a pharmacist", out["reason"])

    def test_a_credit_note_of_dispensed_medicine_is_refused(self):
        cn = desk_body("Sales Invoice", "SI-9", [self.item(qty=-21, sales_order="SO-1")], is_return=1, against="SI-1")
        self.assertIn("cannot be taken back", self.call("/rxc/desk/invoice", cn)[1]["reason"])

    def test_a_drafts_save_is_never_judged(self):
        body = desk_body("Sales Invoice", "SI-1", [self.item()])
        body["context"]["event"] = "validate"
        self.assertEqual(self.call("/rxc/desk/invoice", body), (200, {"verdict": "allow"}))


class WebServer(unittest.TestCase):
    def test_the_real_server_answers_a_signed_call_and_health(self):
        shop = FakeShop().pharmacy()
        svc = app.Service(CONF, api=shop)
        import io
        srv = app.make_server(svc, 0, log=io.StringIO())
        port = srv.server_address[1]
        t = threading.Thread(target=srv.serve_forever, daemon=True)
        t.start()
        try:
            raw = json.dumps(till_body([("BREAD", "Food", 1)])).encode()
            req = urllib.request.Request(f"http://127.0.0.1:{port}/rxc/front", data=raw, method="POST",
                                         headers=dict(sign(raw, "secret-front"), **{"Content-Type": "application/json"}))
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"verdict": "allow"})
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
        finally:
            srv.shutdown()
            srv.server_close()


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(CONF)
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {p: (k, f"secret-{k}") for p, (k, _point) in app.ROUTES.items()}
        self.assertEqual(set(self.routes), set(app.ROUTES))     # every signed point route of the service

    def call(self, path, raw, secret, test=True):
        import base64, hashlib, hmac, time
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        return self.svc.handle("POST", path, h, raw)

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and refused
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
