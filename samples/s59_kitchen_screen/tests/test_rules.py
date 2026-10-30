"""S59's pure core (``ksc.py``): the link's signature, what a link was made for, a ticket kept to its fields, the three
views, and who may move what.

    python3 -m unittest discover -s samples/s59_kitchen_screen/tests -p 'test_*.py'
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import fakeshop as F  # noqa: E402
import ksc  # noqa: E402


def board(tickets=None):
    return ksc.tickets_of({"tickets": [{k: v for k, v in t.items() if k != "store"} for t in (tickets or F.lunch())
                                       if t["store"] == F.STORE]})


class Rules(unittest.TestCase):
    def test_r1_a_link_is_the_retailers_own_signature_for_that_site_record_and_number(self):
        s = ksc.sign(b"k", "a.example", "KSC-SCREEN-00001", 3)
        tok = f"KSC-SCREEN-00001.3.{s}"
        self.assertEqual(ksc.code_of("a.example", tok, [b"k"]), ("KSC-SCREEN-00001", 3))
        self.assertIsNone(ksc.code_of("b.example", tok, [b"k"]))                     # another site
        self.assertIsNone(ksc.code_of("a.example", f"KSC-SCREEN-00001.4.{s}", [b"k"]))   # another number
        self.assertIsNone(ksc.code_of("a.example", tok, [b"other"]))
        self.assertEqual(ksc.code_of("a.example", tok, [b"new", b"k"]), ("KSC-SCREEN-00001", 3))   # the secret before
        self.assertIsNone(ksc.code_of("a.example", f"KSC-SCREEN-00001.0.{ksc.sign(b'k', 'a.example', 'KSC-SCREEN-00001', 0)}", [b"k"]))
        for bad in (None, "", "x.y", "KSC-SCREEN-00001.0." + s, "KSC-SCREEN-00001.٣." + s, "a" * 201):
            self.assertIsNone(ksc.code_of("a.example", bad, [b"k"]), bad)

    def test_r2_a_link_is_made_for_the_screens_kind_store_and_stations(self):
        a = F.screen("S", stations=(F.GRILL, F.FRY))
        self.assertEqual(ksc.made_for(a), ksc.made_for(F.screen("S", stations=(F.FRY, F.GRILL))))   # order does not matter
        for other in (F.screen("S", stations=(F.GRILL,)), F.screen("S", kind="Expo", stations=(F.GRILL, F.FRY)),
                      F.screen("S", store=F.OTHER, stations=(F.GRILL, F.FRY))):
            self.assertNotEqual(ksc.made_for(a), ksc.made_for(other))

    def test_r3_a_ticket_keeps_only_the_doors_fields_of_their_kinds(self):
        t = F.ticket("ko1", 1, F.GRILL, [dict(F.line("BURGER", "B" * 500, note="<img src=x>"), price=9.5)])
        t.update(customer="Ann", total=19.0)
        c = ksc.clean_ticket(t)
        self.assertNotIn("customer", c)
        self.assertNotIn("price", c["lines"][0])
        self.assertEqual(len(c["lines"][0]["item_name"]), 140)
        self.assertEqual(c["lines"][0]["note"], "<img src=x>")        # kept as text: the page puts it as text
        for bad in (dict(t, state="cooking"), dict(t, kind="comp"), dict(t, ticket=0), dict(t, ticket="1"),
                    dict(t, kitchen_order="../x"), "x", None):
            self.assertIsNone(ksc.clean_ticket(bad), bad)

    def test_r4_a_station_view_is_its_stations_live_tickets_and_the_recall(self):
        ts = board()
        ts[0]["state"] = "bumped"
        ts[0]["state_at"] = "2026-10-30 19:04:00"
        v = ksc.station_view(ts, [F.GRILL])
        self.assertEqual([(t["kitchen_order"], t["ticket"]) for t in v["tickets"]], [("ko2", 1)])
        self.assertEqual([(t["kitchen_order"], t["ticket"]) for t in v["recall"]], [("ko1", 1)])

    def test_r5_what_waits_counts_dishes_not_ready_less_a_void(self):
        ts = board(F.lunch() + [F.ticket("ko1", 3, F.FRY, [F.line("FRIES", "Fries", 1)], kind="void")])
        self.assertIn({"item_code": "FRIES", "item_name": "Fries", "qty": 2}, ksc.waiting(ts))
        ts = board()
        for t in ts:
            if t["kitchen_order"] == "ko1":
                t["state"] = "ready"
        self.assertEqual([d["item_code"] for d in ksc.waiting(ts)], ["BEER", "STEAK"])

    def test_r6_an_order_is_ready_when_every_send_ticket_is_and_leaves_when_all_are_bumped(self):
        ts = board()
        ts[0]["state"] = "ready"
        self.assertFalse(ksc.expo_view(ts)["orders"][0]["bump"])          # the fries are not ready
        ts[1]["state"] = "bumped"
        self.assertTrue(ksc.expo_view(ts)["orders"][0]["bump"])
        self.assertEqual(ksc.board_view(ts, False)["ready"], ["42"])
        ts[0]["state"] = "bumped"
        self.assertEqual(ksc.board_view(ts, True), {"preparing": ["Table 12"], "ready": []})
        self.assertEqual([o["kitchen_order"] for o in ksc.expo_view(ts)["orders"]], ["ko2"])
        void_only = board([F.ticket("kv", 1, F.GRILL, [F.line("X", "X")], kind="void")])
        self.assertEqual(ksc.board_view(void_only, True), {"preparing": [], "ready": []})   # a void is never a number

    def test_r6b_the_expo_card_leaves_with_its_dishes_and_times_its_oldest_open_one(self):
        ts = board(F.lunch() + [F.ticket("ko1", 3, F.FRY, [F.line("FRIES", "Fries", 1)], kind="void")])
        for t in ts:
            if t["kitchen_order"] == "ko1" and t["kind"] == "send":
                t["state"] = "bumped"
        self.assertEqual([c["kitchen_order"] for c in ksc.expo_view(ts)["orders"]], ["ko2"])   # its void is the fryer's
        ts = board([F.ticket("k", 1, F.GRILL, [F.line("A", "A")], state="bumped", sent_at="2026-10-30 18:00:00"),
                    F.ticket("k", 2, F.GRILL, [F.line("B", "B")], sent_at="2026-10-30 19:00:00")])
        self.assertEqual(ksc.expo_view(ts)["orders"][0]["sent_at"], "2026-10-30 19:00:00")

    def test_r7b_a_busy_board_keeps_its_newest_tickets(self):
        many = [F.ticket(f"o{i}", 1, F.BAR, [F.line("X", "X")]) for i in range(ksc.BOARD_MAX)] + [F.ticket("new", 1, F.GRILL, [F.line("A", "A")])]
        ts = board(many)
        self.assertEqual(len(ts), ksc.BOARD_MAX)
        self.assertEqual([t["kitchen_order"] for t in ksc.station_view(ts, [F.GRILL])["tickets"]], ["new"])

    def test_r7_who_may_move_what(self):
        ts = board()
        grill, fry = ts[0], ts[1]
        self.assertEqual(ksc.may_move("Station", [F.GRILL], grill, "started"), "")
        self.assertEqual(ksc.may_move("Station", [F.GRILL], grill, "new"), "")       # the same step: the door says already
        self.assertEqual(ksc.may_move("Station", [F.GRILL], grill, "ready"), "step")
        self.assertEqual(ksc.may_move("Station", [F.GRILL], fry, "started"), "not_yours")
        self.assertEqual(ksc.may_move("Station", [F.GRILL], None, "started"), "gone")
        self.assertEqual(ksc.may_move("Board", [], grill, "started"), "board")
        self.assertEqual(ksc.may_move("Expo", [], grill, "started"), "not_yours")
        grill["state"] = "ready"
        self.assertEqual(ksc.may_move("Expo", [], grill, "bumped"), "")

    def test_r8_the_look_takes_only_a_colour_and_known_words(self):
        self.assertEqual(ksc.look({"accent": "red;background:url(x)", "language": "Klingon", "look": "Neon"}),
                         {"mode": "dark", "accent": "", "lang": "en", "warn": 8, "late": 15, "size": "standard"})
        self.assertEqual(ksc.look({"slip_size": "Huge;x"})["size"], "standard")       # only the four steps
        self.assertEqual(ksc.look({"slip_size": "Extra large"})["size"], "xlarge")
        self.assertEqual(ksc.look({"warn_min": 20, "late_min": 10})["late"], 21)    # red always after amber

    def test_r9_the_sold_out_list_is_the_boards_dishes_and_what_is_already_out(self):
        self.assertEqual([d["item_code"] for d in ksc.dishes(board())], ["BEER", "BURGER", "CHEESE", "FRIES", "STEAK"])
        rows = [{"item_code": "SOUP", "sold_out": 1, "available": False}, {"item_code": "TEA", "sold_out": 0, "available": True},
                {"item_code": "PIE", "sold_out": 0, "available": False, "reason": "hours"}]
        self.assertEqual(ksc.sold_out_of(rows), [{"item_code": "SOUP"}])                  # not an item out of its hours


if __name__ == "__main__":
    unittest.main()
