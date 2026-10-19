"""apply_config.py against an in-memory shop: run twice and nothing doubles; --remove undoes only what it made, on the
shop it made it on."""

import copy
import json
import os
import pathlib
import sys
import tempfile
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
os.environ.setdefault("PP_BASE", "https://shop-a.example")
import apply_config as C  # noqa: E402

CONF = json.load(open(HERE.parent / "config.json"))


class Shop:
    def __init__(self):
        self.db = {("Stock Settings", "Stock Settings"): {"allow_existing_serial_no": 1, "disable_serial_no_and_batch_selector": 0,
                                                          "pick_serial_and_batch_based_on": "FIFO"}}
        self.n = 0

    def get(self, dt, name):
        d = self.db.get((dt, name))
        return copy.deepcopy(d) if d is not None else None

    def list(self, dt, filters, fields, parent=None):
        rows = [dict(v, name=k[1]) for k, v in self.db.items() if k[0] == dt]
        for f, op, val in filters:
            rows = [r for r in rows if (r.get(f) in val if op == "in" else r.get(f) == val)]
        return rows

    def insert(self, dt, doc):
        self.n += 1
        name = {"Warehouse": f"{doc.get('warehouse_name')} - DR", "Item": doc.get("item_code")}.get(dt, f"{dt}-{self.n}")
        self.db[(dt, name)] = dict(doc)
        return dict(doc, name=name)

    def update(self, dt, name, fields):
        self.db[(dt, name)].update(fields)

    def delete(self, dt, name):
        del self.db[(dt, name)]


class Config(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.p = unittest.mock.patch.object(C, "HERE", self.dir.name)
        self.p.start()
        self.quiet = lambda *_: None

    def tearDown(self):
        self.p.stop()
        self.dir.cleanup()

    def test_twice_then_remove_puts_the_shop_back(self):
        s = Shop()
        start = copy.deepcopy(s.db)
        C.apply(s, CONF, self.quiet)
        once = copy.deepcopy(s.db)
        C.apply(s, CONF, self.quiet)
        self.assertEqual(s.db, once, "a second run changed something")
        self.assertEqual(s.db[("Stock Settings", "Stock Settings")]["pick_serial_and_batch_based_on"], "Expiry")
        C.remove(s, CONF, self.quiet)
        self.assertEqual(s.db, start)

    def test_a_record_already_in_the_shop_is_never_touched_by_remove(self):
        s = Shop()
        s.db[("Warehouse", "PP USN Defective - DR")] = {"warehouse_name": "PP USN Defective", "company": CONF["company"], "disabled": 0}
        C.apply(s, CONF, self.quiet)
        C.remove(s, CONF, self.quiet)
        self.assertEqual(s.db[("Warehouse", "PP USN Defective - DR")]["disabled"], 0)

    def test_the_before_file_belongs_to_one_shop(self):
        s = Shop()
        C.apply(s, CONF, self.quiet)
        with unittest.mock.patch.dict(os.environ, {"PP_BASE": "https://shop-b.example"}):
            self.assertEqual(C.read_before()["made"], [])


if __name__ == "__main__":
    unittest.main()
