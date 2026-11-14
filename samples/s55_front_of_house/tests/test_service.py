"""S55's laptop tests: the real service, a stand-in for the shop and its open-check door (``fakeshop.py``), presses
signed exactly as the shop signs them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s55_front_of_house/tests -p 'test_*.py'

On our test bench the real Desk buttons were pressed and the checks opened on a real till's floor; these prove the
service's own duties fast, and are what the mutation canaries turn RED."""

import base64
import contextlib
import datetime
import hashlib
import hmac
import io
import json
import os
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [HERE, os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import fakeshop as fs  # noqa: E402
import foh  # noqa: E402

SECRETS = {"book": "s55-book", "seat": "s55-seat", "noshow": "s55-noshow", "cancel": "s55-cancel", "change": "s55-change"}
NOW = datetime.datetime(2026, 10, 29, 17, 0, tzinfo=datetime.timezone.utc).timestamp()
RES, WAIT = "PP FOH Reservation", "PP FOH Waitlist Entry"


def body(doctype, names):
    return {"point": "desk_action/1", "context": {"v": 1, "action": "a1", "label": "x", "user": "host@x", "lang": "en",
                                                   "idempotency_key": "k1", "inputs": {},
                                                   "records": [{"doctype": doctype, "name": n, "fields": {"name": n}}
                                                               for n in names]}}


def signed(payload, secret, ts=None):
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ts = str(int(ts or time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}, raw


class Keys:
    def __init__(self):
        self.n = 0

    def __call__(self):
        self.n += 1
        return f"key-{self.n}"


class ServiceTest(unittest.TestCase):
    def svc(self, shop, now=NOW):
        conf = {f"PP_SECRET_{k.upper()}": v for k, v in SECRETS.items()}
        return app.Service(conf, tenant=shop, now=lambda: now, new_key=Keys())

    def press(self, svc, path, doctype, name, secret=None):
        sub = app.SUBS[path]
        h, raw = signed(body(doctype, [name]), secret or SECRETS[sub])
        return svc.handle("POST", path, h, raw)

    def said(self, out):
        return out[1]["message"]["body"]

    # ── the press itself ──
    def test_p1_an_unsigned_or_wrongly_signed_press_is_refused(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")])
        s = self.svc(shop)
        self.assertEqual(self.press(s, "/press/book", RES, "R1", secret="wrong")[0], 401)
        self.assertEqual(self.press(s, "/press/book", RES, "R1", secret=SECRETS["seat"])[0], 401)   # another button's
        h, raw = signed(body(RES, ["R1"]), SECRETS["book"], ts=time.time() - 3600)
        self.assertEqual(s.handle("POST", "/press/book", h, raw)[0], 401)
        self.assertEqual(shop.calls, [])

    def test_p2_a_press_on_the_wrong_record_is_refused_before_anything_is_read(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], [fs.waiting("W1")])
        s = self.svc(shop)
        self.assertEqual(self.press(s, "/press/book", WAIT, "W1")[0], 400)        # Book is a reservation's
        self.assertEqual(self.press(s, "/press/noshow", "Item", "R1")[0], 400)
        h, raw = signed({"point": "desk_action/1", "context": {"v": 1, "records": [
            {"doctype": RES, "name": "R1"}, {"doctype": RES, "name": "R2"}]}}, SECRETS["seat"])
        self.assertEqual(s.handle("POST", "/press/seat", h, raw)[0], 400)          # one record a press
        self.assertEqual(shop.calls, [])

    def test_p3_the_apps_user_refused_is_said_in_words(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], refuse=("GET", 403))
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(out[0], 200)
        self.assertIn("may not read or write", self.said(out))

    def test_p4_a_lost_answer_from_the_shop_is_a_502_never_a_word_of_success(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], refuse=("GET", None))
        self.assertEqual(self.press(self.svc(shop), "/press/book", RES, "R1")[0], 502)

    def test_p5_a_502_logs_what_the_shop_answered_and_nothing_of_the_press(self):
        # cd-09, 11-05: the shop refused the press stamp's save in its own words, and the log said only 502
        said = "Could not find Company: Old Name"
        shop = fs.FakeTenant(waitlist=[fs.waiting("W1")], refuse=("PUT", 417, "LinkValidationError", said))
        h, raw = signed(body(WAIT, ["W1"]), SECRETS["seat"])
        h["X-iVendNext-Request-Id"] = "r-1"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(app.handle(self.svc(shop), "POST", "/press/seat", h, raw)[0], 502)
        line = json.loads(out.getvalue())
        self.assertEqual({k: line[k] for k in ("request", "status", "call", "kind", "said")},
                         {"request": "r-1", "status": 502, "call": "PUT PP FOH Store -> HTTP 417", "kind": "LinkValidationError",
                          "said": said})
        for word in (SECRETS["seat"], h["X-iVendNext-Signature"], "Ben", "Ode", "7700"):
            self.assertNotIn(word, out.getvalue())
        out = io.StringIO()
        with contextlib.redirect_stdout(out):                       # an answered press logs its line alone
            app.handle(self.svc(fs.FakeTenant(waitlist=[fs.waiting("W1")])), "POST", "/press/seat", *signed(body(WAIT, ["W1"]), SECRETS["seat"]))
        self.assertEqual(set(json.loads(out.getvalue())), {"request", "route", "status", "ms"})

    # ── Book: the double-booking guard ──
    def test_b1_a_free_table_is_held(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")])
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")
        self.assertIn("Table 12 is held for 4 from 19:00 to 20:30", self.said(out))
        self.assertEqual(shop.settings[fs.CO]["stores"][0]["run_started"], "")   # the stamp is cleared after

    def test_b2_an_overlapping_booking_is_refused_and_named(self):
        shop = fs.FakeTenant([fs.booking("R0", "19:30:00", party=2), fs.booking("R1", "19:00:00", status="Requested")])
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(out[1]["message"]["level"], "warning")
        self.assertIn("Table 12 is booked from 19:30 to 21:00 (R0, 2 guests)", self.said(out))
        self.assertEqual(shop.res["R1"]["status"], "Requested")
        self.assertIn("R0", shop.res["R1"]["app_note"])

    def test_b2b_a_booked_reservation_moved_onto_another_is_released(self):
        shop = fs.FakeTenant([fs.booking("R0", "20:00:00"), fs.booking("R1", "19:00:00", status="Booked")])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Requested")                  # it no longer holds the table

    def test_b3_back_to_back_and_other_tables_do_not_clash(self):
        shop = fs.FakeTenant([fs.booking("R0", "20:30:00"), fs.booking("R2", "19:00:00", place=fs.T14),
                              fs.booking("R3", "19:00:00", status="Requested"),
                              fs.booking("R4", "19:00:00", status="Cancelled"),
                              fs.booking("R1", "19:00:00", status="Requested")])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")

    def test_b4_the_booking_and_the_stores_length_are_used(self):
        shop = fs.FakeTenant([fs.booking("R0", "20:15:00"), fs.booking("R1", "19:00:00", status="Requested", minutes=60)])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")                     # 19:00-20:00 against 20:15
        shop = fs.FakeTenant([fs.booking("R0", "20:15:00"), fs.booking("R1", "19:00:00", status="Requested")],
                             settings_=fs.settings(minutes=120))
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Requested")                  # 19:00-21:00 against 20:15

    def test_b5_a_booking_running_past_midnight_holds_the_next_day(self):
        shop = fs.FakeTenant([fs.booking("R0", "23:30:00", date="2026-10-28", minutes=120),
                              fs.booking("R1", "00:30:00", date="2026-10-29", status="Requested")])
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Requested")
        self.assertIn("23:30 to 01:30 on 28 Oct", self.said(out))

    def test_b6_no_table_is_booked_without_a_hold(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", place=None, status="Requested")])
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")
        self.assertIn("no table held", self.said(out))

    def test_b7b_a_press_at_another_store_does_not_wait(self):
        st = fs.settings()
        other = dict(st["stores"][0], name="ROW-2", store="Another Store")
        other["run_started"] = datetime.datetime.fromtimestamp(NOW - 5, datetime.timezone.utc).isoformat(timespec="seconds")
        st["stores"].append(other)
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], settings_=st)
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")

    def test_b7c_a_save_at_another_store_is_read_again_not_busy(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")])
        shop.other_store_saves = ("any",)
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")

    def test_b7d_the_stamp_clears_when_another_store_saves_meanwhile(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")])
        shop.other_store_saves = ("clear",)
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.settings[fs.CO]["stores"][0]["run_started"], "")

    def test_b7_one_press_at_a_time_per_store(self):
        st = fs.settings()
        st["stores"][0]["run_started"] = datetime.datetime.fromtimestamp(NOW - 5, datetime.timezone.utc).isoformat(timespec="seconds")
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], settings_=st)
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertIn("Another press", self.said(out))
        self.assertEqual(shop.res["R1"]["status"], "Requested")
        st["stores"][0]["run_started"] = datetime.datetime.fromtimestamp(NOW - 120, datetime.timezone.utc).isoformat(timespec="seconds")
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], settings_=st)
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")                     # a lapsed stamp holds nothing

    def test_b8_only_an_open_booking_is_booked_and_a_store_needs_its_row(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Seated")])
        self.assertIn("is Seated", self.said(self.press(self.svc(shop), "/press/book", RES, "R1")))
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested", store="Other - BC")])
        self.assertIn("has no row", self.said(self.press(self.svc(shop), "/press/book", RES, "R1")))
        self.assertEqual(shop.res["R1"]["status"], "Requested")

    def test_b9_a_booked_reservation_pressed_again_stays_booked(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Booked")])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Booked")                     # never its own clash

    # ── Seat: one check, through the door ──
    def test_s1_seat_opens_the_check_with_the_party_and_nothing_of_the_guest(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", deposit_sale="ACC-PSINV-0007", deposit_amount=50)])
        out = self.press(self.svc(shop), "/press/seat", RES, "R1")
        (args, check) = shop.keys["key-1"]
        self.assertEqual(args, {"store": fs.STORE, "pos_profile": fs.REG, "place": fs.T12, "covers": 4,
                                "label": "R1 · 4 · deposit 50.00", "source": "front_of_house", "source_ref": "R1"})
        self.assertEqual((shop.res["R1"]["status"], shop.res["R1"]["check_name"]), ("Seated", "CHK-0001"))
        self.assertIn("seated at Table 12: its check CHK-0001 is open on the till for 4 guests", self.said(out))
        sent = json.dumps(shop.sent)
        for word in ("Ana", "Lima", "912", "CUST-ANA", "birthday"):
            self.assertNotIn(word, sent)

    def test_s2_the_key_is_written_after_the_checks_and_before_the_door_under_the_stamp(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")])
        self.press(self.svc(shop), "/press/seat", RES, "R1")
        c = shop.calls
        key_put = next(i for i, x in enumerate(c) if x == f"PUT {RES}")
        self.assertLess(c.index(f"LIST {RES}"), key_put)                         # the clash check first
        self.assertLess(c.index("CALL floor_status"), key_put)                   # the floor read first
        self.assertLess(key_put, c.index("CALL check_open"))                     # the key before the door
        stamps = [i for i, x in enumerate(c) if x == "PUT PP FOH Store"]
        self.assertEqual(len(stamps), 2)
        self.assertLess(stamps[0], c.index(f"LIST {RES}"))
        self.assertGreater(stamps[1], c.index("CALL check_open"))                # the stamp spans the door's call
        keyed = next(b for b in shop.sent if isinstance(b, dict) and "seat_key" in b)
        self.assertEqual((keyed["seat_key"], json.loads(keyed["seat_request"])["key"]), ("key-1", "key-1"))

    def test_s3_a_lost_answer_then_a_second_press_opens_one_check(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], lose_open=1)
        s = self.svc(shop)
        self.assertEqual(self.press(s, "/press/seat", RES, "R1")[0], 502)        # Desk: check the record first
        self.assertEqual(shop.res["R1"]["seat_key"], "key-1")                    # the key stays
        out = self.press(s, "/press/seat", RES, "R1")
        self.assertEqual(len(shop.keys), 1)
        self.assertEqual(len(shop.checks), 1)
        self.assertEqual(shop.res["R1"]["check_name"], "CHK-0001")
        self.assertIn("CHK-0001", self.said(out))

    def test_s4_a_seated_party_is_never_seated_twice(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")])
        s = self.svc(shop)
        self.press(s, "/press/seat", RES, "R1")
        out = self.press(s, "/press/seat", RES, "R1")
        self.assertIn("already seated", self.said(out))
        self.assertEqual(shop.calls.count("CALL check_open"), 1)

    def test_s5_a_second_press_while_one_seats_is_told_to_wait_and_writes_no_key(self):
        st = fs.settings()
        st["stores"][0]["run_started"] = datetime.datetime.fromtimestamp(NOW - 5, datetime.timezone.utc).isoformat(timespec="seconds")
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], settings_=st)
        out = self.press(self.svc(shop), "/press/seat", RES, "R1")
        self.assertIn("Another press", self.said(out))
        self.assertEqual((shop.res["R1"]["seat_key"], shop.keys), ("", {}))
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], stale_seat=1)     # the record changed since it was read
        out = self.press(self.svc(shop), "/press/seat", RES, "R1")
        self.assertIn("Another press", self.said(out))
        self.assertEqual(shop.keys, {})

    def test_s6_a_table_with_an_open_check_is_refused_unless_the_store_allows_it(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], open_checks=[{"check": "CHK-0900", "place": fs.T12}])
        out = self.press(self.svc(shop), "/press/seat", RES, "R1")
        self.assertIn("Table 12 has an open check", self.said(out))
        self.assertNotIn("CALL check_open", shop.calls)
        self.assertEqual((shop.res["R1"]["seat_key"], shop.res["R1"]["status"]), ("", "Booked"))   # the key cleared
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], open_checks=[{"check": "CHK-0900", "place": fs.T12}],
                             settings_=fs.settings(second_check=1))
        self.press(self.svc(shop), "/press/seat", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Seated")

    def test_s7_a_walk_in_is_never_seated_on_a_table_booked_within_its_stay(self):
        shop = fs.FakeTenant([fs.booking("R0", "20:00:00", place=fs.T14, party=6)], [fs.waiting("W1")])
        out = self.press(self.svc(shop), "/press/seat", WAIT, "W1")                 # 19:00 + 90 minutes
        self.assertIn("Table 14 is booked from 20:00 to 21:30 (R0, 6 guests)", self.said(out))
        self.assertNotIn("CALL check_open", shop.calls)
        self.assertEqual(shop.wait["W1"]["seat_key"], "")
        shop = fs.FakeTenant([fs.booking("R0", "21:00:00", place=fs.T14)], [fs.waiting("W1")])
        out = self.press(self.svc(shop), "/press/seat", WAIT, "W1")
        self.assertEqual((shop.wait["W1"]["status"], shop.wait["W1"]["check_name"]), ("Seated", "CHK-0001"))
        self.assertEqual(shop.keys["key-1"][0]["label"], "W1 · 2")

    def test_s8_a_door_refusal_is_said_and_the_key_cleared(self):
        cases = {("ProfileNotAssignedError", 417): "not assigned to register Bistro R1",
                 ("PermissionError", 403): "open a check and see the checks",
                 ("TableServiceOffError", 417): "Table Service is off on register Bistro R1",
                 ("CheckRequestError", 417): "That place is switched off"}
        for (kind, code), words in cases.items():
            shop = fs.FakeTenant([fs.booking("R1", "19:00:00")],
                                 door_refuse=(kind, code, "That place is switched off. Pick another."))
            out = self.press(self.svc(shop), "/press/seat", RES, "R1")
            self.assertIn(words, self.said(out), kind)
            self.assertEqual((shop.res["R1"]["seat_key"], shop.res["R1"]["status"]), ("", "Booked"), kind)

    def test_s8b_the_floor_refusing_the_apps_user_is_said_and_nothing_is_written(self):
        # cd-09, 11-05: the till's floor read refuses a user with no register at the store before the door is asked
        cases = {("ProfileNotAssignedError", 417): "not assigned to register Bistro R1",
                 ("PermissionError", 403): "open a check and see the checks"}
        for (kind, code), words in cases.items():
            shop = fs.FakeTenant([fs.booking("R1", "19:00:00")],
                                 floor_refuse=(kind, code, "You are not assigned to this register at this store."))
            out = self.press(self.svc(shop), "/press/seat", RES, "R1")
            self.assertEqual(out[0], 200, kind)
            self.assertIn(words, self.said(out), kind)
            self.assertEqual((shop.res["R1"]["seat_key"], shop.res["R1"]["status"], shop.keys), ("", "Booked", {}), kind)
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], floor_refuse=("", None, ""))     # no answer: the host checks
        self.assertEqual(self.press(self.svc(shop), "/press/seat", RES, "R1")[0], 502)

    def test_s9_a_party_needs_its_table_and_a_closed_booking_is_not_seated(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", place=None), fs.booking("R2", "19:00:00", status="No-show")])
        s = self.svc(shop)
        self.assertIn("Choose the table", self.said(self.press(s, "/press/seat", RES, "R1")))
        self.assertIn("is No-show", self.said(self.press(s, "/press/seat", RES, "R2")))
        self.assertNotIn("CALL check_open", shop.calls)

    def test_s10_a_refused_retry_keeps_its_key(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], lose_open=1)
        s = self.svc(shop)
        self.assertEqual(self.press(s, "/press/seat", RES, "R1")[0], 502)        # the check opened; the answer lost
        shop.door_refuse = ("TableServiceOffError", 417, "Table service is off.")    # switched off before the retry
        out = self.press(s, "/press/seat", RES, "R1")
        self.assertIn("may already have opened its check", self.said(out))
        self.assertEqual(shop.res["R1"]["seat_key"], "key-1")                    # kept: the next press finds the check
        shop.door_refuse = None
        self.press(s, "/press/seat", RES, "R1")
        self.assertEqual((len(shop.checks), shop.res["R1"]["check_name"]), (1, "CHK-0001"))

    def test_s10b_a_retry_refused_by_the_checks_own_body_starts_afresh(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], lose_open=1)
        s = self.svc(shop)
        self.press(s, "/press/seat", RES, "R1")
        shop.keys.clear()                           # as if the lost first send had opened nothing
        shop.checks.clear()
        shop.door_refuse = ("CheckRequestError", 417, "That place is switched off. Pick another.")
        out = self.press(s, "/press/seat", RES, "R1")
        self.assertIn("That place is switched off", self.said(out))
        self.assertEqual(shop.res["R1"]["seat_key"], "")                     # the host can choose another table

    def test_s11_a_refused_check_writes_no_key_at_all(self):
        shop = fs.FakeTenant([fs.booking("R0", "19:30:00", party=2), fs.booking("R1", "19:00:00", place=fs.T14)],
                             [fs.waiting("W1", place=fs.T12)])
        self.press(self.svc(shop), "/press/seat", WAIT, "W1")
        self.assertFalse(any("seat_key" in b for b in shop.sent if isinstance(b, dict)))
        self.assertEqual(shop.wait["W1"]["seat_key"], "")

    def test_s12_a_retry_after_an_edit_seats_where_the_check_opened(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], lose_open=1)
        s = self.svc(shop)
        self.press(s, "/press/seat", RES, "R1")
        shop.res["R1"]["place"], shop.res["R1"]["place_label"] = fs.T14, "Table 14"   # moved before the retry
        out = self.press(s, "/press/seat", RES, "R1")
        self.assertEqual((shop.res["R1"]["place"], shop.checks[0]["place"]), (fs.T12, fs.T12))
        self.assertIn(f"seated at {fs.T12}", self.said(out))

    def test_s13_a_party_seated_and_gone_does_not_hold_its_booked_time(self):
        shop = fs.FakeTenant([fs.booking("R0", "18:30:00", status="Seated", check_name="CHK-0900")],
                             [fs.waiting("W1", place=fs.T12)])
        self.press(self.svc(shop), "/press/seat", WAIT, "W1")                        # the floor shows T12 free
        self.assertEqual(shop.wait["W1"]["status"], "Seated")

    # ── Change booking ──
    def test_c1_change_booking_releases_the_hold_and_book_holds_the_new_slot(self):
        shop = fs.FakeTenant([fs.booking("R0", "21:00:00", place=fs.T14), fs.booking("R1", "19:00:00")])
        s = self.svc(shop)
        self.assertIn("no longer held", self.said(self.press(s, "/press/change", RES, "R1")))
        self.assertEqual(shop.res["R1"]["status"], "Requested")
        shop.res["R1"].update(place=fs.T14, place_label="Table 14", booking_time="20:00:00")
        self.press(s, "/press/book", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "Requested")                    # 20:00-21:30 against 21:00
        shop.res["R2"] = fs.booking("R2", "19:00:00", status="Requested")
        self.press(s, "/press/book", RES, "R2")
        self.assertEqual(shop.res["R2"]["status"], "Booked")                       # T12 at 19:00 is free again

    def test_c2_only_a_booked_reservation_not_being_seated_is_changed(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested"),
                              fs.booking("R2", "19:00:00", place=fs.T14, seat_key="k", seat_request="{}")])
        s = self.svc(shop)
        self.assertIn("is Requested", self.said(self.press(s, "/press/change", RES, "R1")))
        self.assertIn("not being seated", self.said(self.press(s, "/press/change", RES, "R2")))
        self.assertEqual(shop.res["R2"]["status"], "Booked")

    # ── No-show and Cancel ──
    def test_n1_a_no_show_writes_the_stores_deposit_rule(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", deposit_sale="ACC-PSINV-0007", deposit_amount=50)])
        out = self.press(self.svc(shop), "/press/noshow", RES, "R1")
        self.assertEqual(shop.res["R1"]["status"], "No-show")
        self.assertIn("keep it", shop.res["R1"]["app_note"])
        self.assertIn("ACC-PSINV-0007, 50.00", self.said(out))
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", deposit_sale="ACC-PSINV-0007", deposit_amount=50)],
                             settings_=fs.settings(no_show_deposit="Return it"))
        self.press(self.svc(shop), "/press/noshow", RES, "R1")
        self.assertIn("return it", shop.res["R1"]["app_note"])

    def test_n3_an_unfinished_seat_is_never_closed_over(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")], lose_open=1)
        s = self.svc(shop)
        self.press(s, "/press/seat", RES, "R1")
        for path in ("/press/noshow", "/press/cancel"):
            self.assertIn("did not finish", self.said(self.press(s, path, RES, "R1")))
        self.assertEqual(shop.res["R1"]["status"], "Booked")

    def test_n2_cancel_frees_the_table_and_a_closed_booking_stays_closed(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00"), fs.booking("R2", "19:00:00", place=fs.T14, status="Seated")])
        s = self.svc(shop)
        self.assertIn("table is free again", self.said(self.press(s, "/press/cancel", RES, "R1")))
        self.assertEqual(shop.res["R1"]["status"], "Cancelled")
        self.assertIn("is Seated", self.said(self.press(s, "/press/noshow", RES, "R2")))
        self.assertEqual(shop.res["R2"]["status"], "Seated")
        shop.res["R3"] = fs.booking("R3", "19:00:00", status="Requested")
        self.press(s, "/press/book", RES, "R3")
        self.assertEqual(shop.res["R3"]["status"], "Booked")                     # a cancelled booking holds nothing

    def test_n4_cancelling_a_booking_that_never_held_its_table_says_nothing_of_the_table(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00"), fs.booking("R2", "19:00:00", status="Requested")])
        s = self.svc(shop)
        self.assertNotIn("table", self.said(self.press(s, "/press/cancel", RES, "R2")))   # T12 is still R1's
        self.assertEqual(self.hold(shop)[0], "2026-10-29 19:00:00")
        self.assertIn("table is free again", self.said(self.press(s, "/press/noshow", RES, "R1")))

    # ── the till's floor: each press writes the table's next booking on its place ──
    def hold(self, shop, place=fs.T12):
        return shop.places[place]["held_from"], shop.places[place]["held_to"]

    def test_f1_book_writes_the_tables_hold(self):
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00", status="Requested")])
        out = self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(self.hold(shop), ("2026-10-29 20:00:00", "2026-10-29 21:30:00"))
        self.assertEqual(out[1]["message"]["level"], "success")
        floor = shop.call("floor_status", query={"store": fs.STORE})
        self.assertEqual([p.get("held_from") for p in floor["places"]], ["2026-10-29 20:00:00", None])
        put = [b for b in shop.sent if b and "held_from" in b]
        self.assertEqual(put, [{"held_from": "2026-10-29 20:00:00", "held_to": "2026-10-29 21:30:00"}])   # times only

    def test_f2_seat_moves_the_hold_to_the_tables_next_booking_or_clears_it(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00"), fs.booking("R2", "21:00:00")])
        s = self.svc(shop)
        self.press(s, "/press/seat", RES, "R1")
        self.assertEqual(self.hold(shop), ("2026-10-29 21:00:00", "2026-10-29 22:30:00"))   # the next party's
        self.press(s, "/press/cancel", RES, "R2")
        self.assertEqual(self.hold(shop), (None, None))                                   # nothing more tonight
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00")])
        self.press(self.svc(shop), "/press/seat", RES, "R1")
        self.assertEqual((shop.res["R1"]["status"], self.hold(shop)), ("Seated", (None, None)))

    def test_f3_no_show_cancel_and_change_clear_the_hold(self):
        for path, status in (("/press/noshow", "No-show"), ("/press/cancel", "Cancelled"), ("/press/change", "Requested")):
            shop = fs.FakeTenant([fs.booking("R1", "19:30:00")])
            shop.places[fs.T12].update(held_from="2026-10-29 19:30:00", held_to="2026-10-29 21:00:00")
            self.press(self.svc(shop), path, RES, "R1")
            self.assertEqual((shop.res["R1"]["status"], self.hold(shop)), (status, (None, None)), path)

    def test_f4_a_walk_in_seated_keeps_the_tables_later_booking(self):
        shop = fs.FakeTenant([fs.booking("R1", "22:00:00", place=fs.T14)], [fs.waiting("W1", place=fs.T14)])
        self.press(self.svc(shop), "/press/seat", WAIT, "W1")
        self.assertEqual(shop.wait["W1"]["status"], "Seated")
        self.assertEqual(self.hold(shop, fs.T14), ("2026-10-29 22:00:00", "2026-10-29 23:30:00"))

    def test_f5_a_floor_the_app_may_not_write_leaves_the_booking_and_says_so(self):
        for path, status in (("/press/book", "Booked"), ("/press/seat", "Seated"), ("/press/noshow", "No-show"),
                             ("/press/cancel", "Cancelled"), ("/press/change", "Requested")):
            first = "Requested" if path == "/press/book" else "Booked"
            shop = fs.FakeTenant([fs.booking("R1", "19:30:00", status=first, deposit_sale="ACC-PSINV-2026-00063",
                                             deposit_amount=50)], place_right=False)
            out = self.press(self.svc(shop), path, RES, "R1")
            self.assertEqual((out[0], shop.res["R1"]["status"], out[1]["message"]["level"]), (200, status, "warning"), path)
            self.assertTrue(self.said(out).endswith(app.FLOOR_REFUSED.strip()), (path, self.said(out)))   # never cut off
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00", status="Requested")], refuse=("PUT " + app.PLACE, None))
        out = self.press(self.svc(shop), "/press/book", RES, "R1")                  # the place write timed out
        self.assertEqual((shop.res["R1"]["status"], out[1]["message"]["level"]), ("Booked", "warning"))
        self.assertTrue(self.said(out).endswith(app.FLOOR_LOST.strip()))

    def test_f7_after_midnight_a_booking_from_yesterday_still_running_is_the_hold(self):
        shop = fs.FakeTenant([fs.booking("R1", "23:30:00"), fs.booking("R2", "02:00:00", date="2026-10-30")],
                             clock="2026-10-30 00:30:00")
        self.press(self.svc(shop), "/press/cancel", RES, "R2")
        self.assertEqual(self.hold(shop), ("2026-10-29 23:30:00", "2026-10-30 01:00:00"))

    def test_f8_a_book_refused_by_a_clash_leaves_the_table_on_the_booking_that_holds_it(self):
        shop = fs.FakeTenant([fs.booking("R0", "20:00:00"), fs.booking("R1", "19:00:00", status="Booked")])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual((shop.res["R1"]["status"], self.hold(shop)), ("Requested", ("2026-10-29 20:00:00", "2026-10-29 21:30:00")))

    def test_f9_a_booking_that_ended_with_no_press_moves_on_at_the_next_press_anywhere_in_the_store(self):
        shop = fs.FakeTenant([fs.booking("R1", "12:00:00", place=fs.T14), fs.booking("R2", "20:00:00", place=fs.T14),
                              fs.booking("R3", "21:00:00", status="Requested")])
        shop.places[fs.T14].update(held_from="2026-10-29 12:00:00", held_to="2026-10-29 13:30:00")   # lunch, never pressed
        self.press(self.svc(shop), "/press/book", RES, "R3")                               # at another table
        self.assertEqual(self.hold(shop, fs.T14), ("2026-10-29 20:00:00", "2026-10-29 21:30:00"))
        self.assertEqual(self.hold(shop), ("2026-10-29 21:00:00", "2026-10-29 22:30:00"))

    def test_f10_on_update_day_one_press_tells_every_booked_table(self):
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00"), fs.booking("R2", "21:00:00", place=fs.T14),
                              fs.booking("R3", "22:00:00", place=fs.T14, status="Requested")])
        self.press(self.svc(shop), "/press/cancel", RES, "R3")
        self.assertEqual((self.hold(shop)[0], self.hold(shop, fs.T14)[0]), ("2026-10-29 20:00:00", "2026-10-29 21:00:00"))

    def test_f11_a_booking_moved_in_the_list_frees_its_old_table_at_the_next_press(self):
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00", place=fs.T14), fs.booking("R2", "21:00:00", status="Requested",
                                                                                       place=fs.T14)])
        shop.places[fs.T12].update(held_from="2026-10-29 20:00:00", held_to="2026-10-29 21:30:00")   # R1 was on T12
        self.press(self.svc(shop), "/press/noshow", RES, "R2")
        self.assertEqual((self.hold(shop), self.hold(shop, fs.T14)[0]), ((None, None), "2026-10-29 20:00:00"))

    def test_f13_another_stores_tables_are_never_touched(self):
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00", status="Requested")])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual(self.hold(shop, fs.OTHER_PLACE), ("2026-10-29 21:00:00", "2026-10-29 22:30:00"))

    def test_f12_only_the_tables_that_differ_are_written(self):
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00", status="Requested"), fs.booking("R2", "21:00:00", place=fs.T14)])
        shop.places[fs.T14].update(held_from="2026-10-29 21:00:00", held_to="2026-10-29 22:30:00")
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertEqual([b for b in shop.sent if b and "held_from" in b],
                         [{"held_from": "2026-10-29 20:00:00", "held_to": "2026-10-29 21:30:00"}])   # T12 only

    # ── the store's own clock: a store in another zone from its site (the site New York, 19:00 there at 23:00 UTC) ──
    NY = datetime.datetime(2026, 10, 29, 23, 0, tzinfo=datetime.timezone.utc).timestamp()

    def test_z1_a_bookings_time_is_the_stores_and_the_floor_gets_the_sites(self):
        shop = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")], zone="America/Los_Angeles")
        out = self.press(self.svc(shop, now=self.NY), "/press/book", RES, "R1")
        self.assertIn("from 19:00 to 20:30", self.said(out))                     # the host's own time, in the answer
        self.assertEqual(self.hold(shop), ("2026-10-29 22:00:00", "2026-10-29 23:30:00"))   # 19:00 Portland, as New York
        # 17:00 in Portland is still to come at 16:00 there, though 17:00 is past on the site's clock
        shop = fs.FakeTenant([fs.booking("R1", "17:00:00", status="Requested")], zone="America/Los_Angeles")
        self.press(self.svc(shop, now=self.NY), "/press/book", RES, "R1")
        self.assertEqual(self.hold(shop), ("2026-10-29 20:00:00", "2026-10-29 21:30:00"))

    def test_z2_seat_reads_now_on_the_stores_clock(self):
        # 19:00 in New York is 16:00 in Portland: a booking at 17:00 there is due within a walk-in's stay
        shop = fs.FakeTenant([fs.booking("R0", "17:00:00")], [fs.waiting("W1", place=fs.T12)], zone="America/Los_Angeles")
        out = self.press(self.svc(shop, now=self.NY), "/press/seat", WAIT, "W1")
        self.assertIn("Not seated: Table 12 is booked from 17:00 to 18:30", self.said(out))
        self.assertEqual(shop.wait["W1"]["status"], "Waiting")

    def test_z3_a_site_that_keeps_the_store_from_the_app_or_an_unknown_zone_keeps_the_sites_time(self):
        for kw in ({"zone": "America/Los_Angeles", "store_right": False}, {"zone": "Not/AZone"}, {"zone": ""}):
            shop = fs.FakeTenant([fs.booking("R1", "19:30:00", status="Requested")], **kw)
            out = self.press(self.svc(shop, now=self.NY), "/press/book", RES, "R1")
            self.assertEqual((out[1]["message"]["level"], self.hold(shop)[0]), ("success", "2026-10-29 19:30:00"), kw)

    def test_f6_a_booking_with_no_table_writes_no_place(self):
        shop = fs.FakeTenant([fs.booking("R1", "20:00:00", status="Requested", place=None)])
        self.press(self.svc(shop), "/press/book", RES, "R1")
        self.assertFalse([c for c in shop.calls if c.startswith("PUT " + app.PLACE)])


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service({f"PP_SECRET_{k.upper()}": v for k, v in SECRETS.items()}, object())
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {p: (k, SECRETS[k]) for p, k in app.SUBS.items()}
        self.assertEqual(set(self.routes), set(app.SUBS))     # every signed point route of the service

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
