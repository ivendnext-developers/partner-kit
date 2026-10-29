"""S56's press answers against the published Desk action contract, and its calls to the open-check door against the
open-check contract (``desk_action.v1.schema.json``, ``open_check.v1.schema.json`` in ``contracts/``, read by
``tools/contracts/check.py``)."""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), os.path.join(ROOT, "tools", "contracts"), HERE]
import check  # noqa: E402
import fakeshop as F  # noqa: E402
import gor  # noqa: E402
from test_service import ORDER, Clock, guest, latte, made, service  # noqa: E402


@unittest.skipUnless(check.available(), "the contracts folder is missing from this copy of the kit")
class ContractTest(unittest.TestCase):
    def test_every_answer_the_press_gives_holds(self):
        for value in (gor.message("GOR-CODE-00001's code is made (number 1)."), gor.message("x " * 400, "warning")):
            self.assertEqual(check.errors("desk_action", "answer", value), [])

    def test_the_calls_to_the_door_hold(self):
        for kind, code in (("Table", "GOR-CODE-00001"), ("Kiosk", "GOR-CODE-00002")):
            shop = F.FakeTenant(codes=[F.code(code, kind=kind, kiosk_name="By the door")])
            svc = service(shop, Clock())
            t = made(shop, svc, code)
            self.assertEqual(guest(svc, "/gor/order", t, key=ORDER, lines=[latte(), {"item_code": "SALAD"}])[1]["state"],
                             "sent")
            opens = [s for s in shop.sent if isinstance(s, dict) and "pos_profile" in s]
            adds = [s for s in shop.sent if isinstance(s, dict) and "lines" in s]
            self.assertEqual((len(opens), len(adds)), (1, 1))
            self.assertEqual(check.errors("open_check", "open_request", opens[0]), [], kind)
            self.assertEqual(check.errors("open_check", "add_request", adds[0]), [], kind)
        self.assertTrue(check.errors("open_check", "open_request", dict(opens[0], source="Guest Ordering!")))   # live


if __name__ == "__main__":
    unittest.main()
