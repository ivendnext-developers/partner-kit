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
        self.assertIn("nothing left to dispense", out["reason"])

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
        self.assertIn("nothing left", self.sell(("AMOX", "Rx", 21), rx="RX1", sale_ref="sale-y", opening="DAY-2")[1]["reason"])
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
        self.assertIn("nothing left to dispense", out["reason"])
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


if __name__ == "__main__":
    unittest.main()
