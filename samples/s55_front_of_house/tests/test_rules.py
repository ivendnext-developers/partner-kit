"""S55's pure core: the shop's times read as numbers, the overlap rule, the check's label and call, the floor, the
deposit's words.

    python3 -m unittest discover -s samples/s55_front_of_house/tests -p 'test_*.py'
"""

import datetime
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import foh  # noqa: E402

D = datetime.datetime


class Rules(unittest.TestCase):
    def test_r1_the_shops_times_are_read_as_numbers(self):
        self.assertEqual(foh.moment("2026-10-29", "9:05:00"), D(2026, 10, 29, 9, 5))      # the shop prints 9:05:00
        self.assertEqual(foh.moment("2026-10-29", "19:30:00.000000"), D(2026, 10, 29, 19, 30))
        self.assertEqual(foh.moment("2026-10-29", "19:30"), D(2026, 10, 29, 19, 30))
        self.assertIsNone(foh.moment("", "19:30"))
        self.assertIsNone(foh.moment("2026-10-29", "late"))

    def test_r2_overlap_is_strict_and_only_held_bookings_count(self):
        mine = foh.span(D(2026, 10, 29, 19, 0), 90)
        row = {foh_store: {"minutes": 90} for foh_store in ("S",)}

        def other(t, status="Booked", **kw):
            return dict({"name": f"R-{t}", "status": status, "store": "S", "booking_date": "2026-10-29",
                         "booking_time": t, "party": 2}, **kw)
        self.assertEqual(foh.clashes(mine, [other("20:30:00"), other("17:30:00")], row), [])     # back to back
        self.assertEqual([o["name"] for o in foh.clashes(mine, [other("20:29:00"), other("17:31:00")], row)],
                         ["R-17:31:00", "R-20:29:00"])                                         # earliest first
        self.assertEqual(foh.clashes(mine, [other("19:00:00", "Requested"), other("19:00:00", "No-show"),
                                            other("19:00:00", "Cancelled")], row), [])
        self.assertEqual(foh.clashes(mine, [other("19:00:00", "Seated")], row), [])     # its open check holds it
        self.assertEqual(foh.clashes(mine, [other("19:00:00", name="ME")], row, exclude="ME"), [])
        self.assertEqual(len(foh.clashes(mine, [other("17:00:00", minutes=150)], row)), 1)      # its own length

    def test_r3_a_length_is_its_own_then_the_stores_then_90_and_bounded(self):
        self.assertEqual(foh.minutes_of({"minutes": 45}, {"minutes": 120}), 45)
        self.assertEqual(foh.minutes_of({"minutes": None}, {"minutes": 120}), 120)
        self.assertEqual(foh.minutes_of({}, {}), 90)
        self.assertEqual(foh.minutes_of({"minutes": 5}, {}), 15)
        self.assertEqual(foh.minutes_of({"minutes": 99999}, {}), 1440)

    def test_r4_the_days_a_clash_can_come_from(self):
        self.assertEqual(foh.days_around(D(2026, 11, 1, 0, 30)), ["2026-10-31", "2026-11-01", "2026-11-02"])

    def test_r5_the_check_carries_the_booking_never_the_guest(self):
        req = foh.seat_request("S", "R1", "k", "FP-1", "FOH-RES-00042", 4, 50)
        self.assertEqual(req, {"store": "S", "pos_profile": "R1", "key": "k", "place": "FP-1", "covers": 4,
                               "label": "FOH-RES-00042 · 4 · deposit 50.00", "source": "front_of_house",
                               "source_ref": "FOH-RES-00042"})
        self.assertNotIn("suggested_customer", req)
        self.assertNotIn("server", req)
        self.assertEqual(foh.label_of("W1", 2, None), "W1 · 2")
        self.assertEqual(foh.label_of("W1", 2, "0"), "W1 · 2")
        self.assertLessEqual(len(foh.seat_request("S", "R", "k", "P", "N" * 300, 1)["source_ref"]), 140)
        self.assertLessEqual(len(foh.SOURCE), 20)

    def test_r6_the_floor_shows_a_table_in_use(self):
        floor = {"places": [{"place": "A", "status": "free", "checks": []}, {"place": "B", "status": "ordered"},
                            {"place": "C", "status": "free", "checks": [{"check": "X"}]}]}
        self.assertEqual([foh.place_busy(floor, p) for p in "ABCD"], [False, True, True, False])

    def test_r7_the_deposit_words(self):
        self.assertEqual(foh.deposit_note("Keep it", "", 50), "")
        self.assertIn("keep it", foh.deposit_note("Keep it", "SALE-1", 50))
        self.assertIn("return it", foh.deposit_note("Return it", "SALE-1", 50))
        self.assertIn("as your booking terms say", foh.deposit_note("Keep it", "SALE-1", 50, cancelled=True))
        self.assertIn("SALE-1, 50.00", foh.deposit_note("Keep it", "SALE-1", "50"))

    def test_r8_an_answer_fits_the_desk(self):
        out = foh.message("Front of house", "x " * 400, "warning", refresh=False)
        self.assertLessEqual(len(out["message"]["body"]), 280)
        self.assertNotIn("refresh", out)

    def test_r9_the_tables_next_booking_is_its_hold(self):
        rows = {"S": {"minutes": 90}}
        now = D(2026, 10, 29, 19, 15)

        def b(name, t, status="Booked", date="2026-10-29", **kw):
            return dict({"name": name, "status": status, "store": "S", "booking_date": date, "booking_time": t}, **kw)

        none = {"held_from": "", "held_to": ""}
        self.assertEqual(foh.next_hold([], rows, now), none)
        self.assertEqual(foh.next_hold([b("R1", "21:00:00")], rows, now),
                         {"held_from": "2026-10-29 21:00:00", "held_to": "2026-10-29 22:30:00"})
        self.assertEqual(foh.next_hold([b("R2", "22:00:00"), b("R1", "20:00:00", minutes=60)], rows, now)["held_from"],
                         "2026-10-29 20:00:00")                                   # the earliest of two
        self.assertEqual(foh.next_hold([b("R1", "20:00:00"), b("R2", "22:00:00")], rows, now)["held_from"],
                         "2026-10-29 20:00:00")                                   # in either order
        self.assertEqual(foh.next_hold([b("R1", "17:00:00"), b("R2", "18:00:00")], rows, now),
                         {"held_from": "2026-10-29 18:00:00", "held_to": "2026-10-29 19:30:00"})   # one over, one not yet
        self.assertEqual(foh.next_hold([b("R1", "16:00:00")], rows, now), none)    # over at 17:30: nothing holds
        self.assertEqual(foh.next_hold([b("R1", "23:30:00", date="2026-10-28")], rows, D(2026, 10, 29, 0, 30)),
                         {"held_from": "2026-10-28 23:30:00", "held_to": "2026-10-29 01:00:00"})   # past midnight
        self.assertEqual(foh.next_hold([b("R1", "20:00:00", "Requested"), b("R2", "20:00:00", "Seated"),
                                        b("R3", "20:00:00", "Cancelled"), b("R4", "20:00:00", "No-show")], rows, now), none)
        self.assertEqual(foh.next_hold([b("R1", "20:00:00", date="2026-10-30")], rows, now)["held_to"],
                         "2026-10-30 21:30:00")                                   # tomorrow's: the till shows it tomorrow


    def test_r10_a_stores_clock_against_its_sites(self):
        ny_now, utc_now = D(2026, 10, 29, 19, 0, 3), D(2026, 10, 29, 23, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(foh.site_offset(ny_now, utc_now), datetime.timedelta(hours=-4))     # to the quarter hour
        self.assertEqual(foh.site_offset(D(2026, 10, 30, 4, 29), utc_now), datetime.timedelta(hours=5, minutes=30))
        portland = foh.Clock(foh.zone_of("America/Los_Angeles"), datetime.timedelta(hours=-4))
        self.assertEqual(portland.site(D(2026, 10, 29, 19, 0)), D(2026, 10, 29, 22, 0))     # 19:00 there is 22:00 here
        self.assertEqual(portland.store(D(2026, 10, 29, 19, 0)), D(2026, 10, 29, 16, 0))
        self.assertEqual(portland.site(D(2026, 10, 29, 21, 30)), D(2026, 10, 30, 0, 30))    # past the site's midnight
        for name in ("", None, "Mars/Olympus", "../etc", 7):
            self.assertIsNone(foh.zone_of(name), name)                  # the site's time, as the till's receipts do
        self.assertEqual(foh.SITE.site(D(2026, 10, 29, 19, 0)), D(2026, 10, 29, 19, 0))
        b = {"name": "R1", "status": "Booked", "store": "S", "booking_date": "2026-10-29", "booking_time": "19:00:00"}
        self.assertEqual(foh.next_hold([b], {"S": {"minutes": 90}}, D(2026, 10, 29, 16, 0), portland),
                         {"held_from": "2026-10-29 22:00:00", "held_to": "2026-10-29 23:30:00"})

    def test_r11_only_the_tables_that_differ_are_told(self):
        rows = {"S": {"minutes": 90}}
        b = {"name": "R1", "status": "Booked", "store": "S", "booking_date": "2026-10-29", "booking_time": "20:00:00",
             "place": "T1"}
        places = [{"name": "T1", "held_from": "2026-10-29 20:00:00.000000", "held_to": "2026-10-29 21:30:00"},
                  {"name": "T2", "held_from": "2026-10-29 12:00:00", "held_to": "2026-10-29 13:30:00"},
                  {"name": "T3", "held_from": None, "held_to": None}]
        self.assertEqual(foh.floor_holds(places, [b], rows, D(2026, 10, 29, 19, 0)),
                         {"T2": {"held_from": "", "held_to": ""}})                # T1 already true, T3 already free
        self.assertEqual(foh.floor_holds(places[2:], [dict(b, place="T3")], rows, D(2026, 10, 29, 19, 0)),
                         {"T3": {"held_from": "2026-10-29 20:00:00", "held_to": "2026-10-29 21:30:00"}})


if __name__ == "__main__":
    unittest.main()
