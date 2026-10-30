"""S59's press answers against the published Desk action contract, and its calls to the station-ticket door against the
station-ticket contract (``desk_action.v1.schema.json``, ``station_ticket.v1.schema.json`` in ``contracts/``, read by
``tools/contracts/check.py``); the stand-in shop's board is the contract's own shape."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), os.path.join(ROOT, "tools", "contracts"), HERE]
import check  # noqa: E402
import fakeshop as F  # noqa: E402
import ksc  # noqa: E402
from test_service import Clock, call, made, service  # noqa: E402

HAS_DOOR = os.path.exists(os.path.join(ROOT, "contracts", "extension_contracts", "station_ticket.v1.schema.json"))


@unittest.skipUnless(check.available() and HAS_DOOR, "the station-ticket contract is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_press_gives_holds(self):
        for value in (ksc.message("KSC-SCREEN-00001's link is made (number 1)."), ksc.message("x " * 400, "warning")):
            self.assertEqual(check.errors("desk_action", "answer", value), [])

    def test_the_stand_in_board_is_the_doors_shape(self):
        shop = F.FakeTenant()
        self.assertEqual(check.errors("station_ticket", "board", shop.call("station_tickets", query={"store": F.STORE})), [])

    def test_the_calls_to_the_door_hold(self):
        shop = F.FakeTenant(screens=[F.screen("KSC-SCREEN-00001")])
        clock = Clock()
        svc = service(shop, clock)
        t = made(shop, svc, "KSC-SCREEN-00001")
        for state in ("started", "ready", "bumped"):
            self.assertEqual(call(svc, "/ksc/move", t, kitchen_order="ko1", ticket=1, state=state)[1]["state"], "moved")
            clock.t += 1
        moves = [b for v, b in shop.sent if v == "station_ticket_move"]
        self.assertEqual(len(moves), 3)
        for b in moves:
            self.assertEqual(check.errors("station_ticket", "move_request", b), [], b)
        self.assertTrue(check.errors("station_ticket", "move_request", dict(moves[0], state="new")))   # live


if __name__ == "__main__":
    unittest.main()
