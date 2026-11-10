"""An in-memory stand-in for one shop's record API, for S63's laptop tests: it names a post row by its sale, refuses a second
(``Duplicate``, as the shop's 409), and filters as the service does. Not the shop: the programme's bench proves the same against
a real one. The shape is S52's ``tests/fake_shop.py``: a defect there is a defect here.
"""

from __future__ import annotations

import copy
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
from shop import Duplicate, ShopError  # noqa: E402

POST, SET = "PP RMC Post", "PP RMC Settings"
STORE = "Harbour Hotel Bar"


class FakeShop:
    def __init__(self, url: str = "https://hotel.example"):
        self.url, self.db, self.lock, self.down = url, {}, threading.Lock(), False

    def put(self, dt, name, **fields):
        self.db.setdefault(dt, {})[name] = dict(fields, name=name, doctype=dt)
        return self.db[dt][name]

    def get(self, dt, name):
        if self.down:
            raise ShopError(0, "unreachable")
        d = self.db.get(dt, {}).get(name)
        return copy.deepcopy(d) if d else None

    def list(self, dt, filters=None, fields=("name",), order_by="", limit=0):
        rows = [d for d in self.db.get(dt, {}).values() if all(d.get(f) == v for f, _, v in filters or [])]
        return [{k: d.get(k) for k in set(fields) | {"name"}} for d in rows]

    def insert(self, doc):
        with self.lock:
            dt, name = doc["doctype"], doc["sale"]
            if name in self.db.get(dt, {}):
                raise Duplicate(409, f"{dt} {name} already exists")
            self.db.setdefault(dt, {})[name] = dict(copy.deepcopy(doc), name=name)
            return name

    def update(self, dt, name, fields):
        with self.lock:
            if name not in self.db.get(dt, {}):
                raise ShopError(404, f"{dt} {name} not found")
            self.db[dt][name].update(copy.deepcopy(fields))
            return self.db[dt][name]


class FakeFeed:
    """The event feed's door, in memory: events stay until ``done``."""

    def __init__(self, events=()):
        self.waiting, self.notes = list(events), {}

    def events(self, limit=100, page=None):
        return list(self.waiting), None, len(self.waiting)

    def done(self, ids):
        self.waiting = [e for e in self.waiting if e["id"] not in ids]
        return len(ids)

    def failed(self, id_, note):
        self.notes[id_] = note


def hotel_shop(system="Simulator", tip_code="TIP", store=STORE) -> FakeShop:
    t = FakeShop()
    t.put(SET, SET, stores=[{"store": store, "hotel_system": system, "connection": "", "charge_code": "FNB", "tip_code": tip_code,
                             "mode_of_payment": "Room Charge"}])
    return t


def sale(t: FakeShop, name: str, room="412", guest="Smith", folio="R-1001 (412 Smith)", paid=(("Room Charge", 120.0),), tip="",
         is_return=0, against=None, store=STORE, chip=()):
    """``chip``: the tips the till's tip chip booked, ((mode, amount), ...): one tip journal per tipped leg, as POS tip.py
    writes them (the sale, "Tip", the mode), and their sum on the sale's ``custom_mpos_tip_amount``."""
    details = [("Room", room), ("Guest", guest), ("Folio", folio), ("Tip", tip)]
    for n, (mode, amount) in enumerate(chip):
        t.put("Journal Entry", f"JV-{name}-{n}", docstatus=1, custom_reference_1=name, custom_reference_2="Tip",
              custom_reference_3=mode, total_debit=amount)
    return t.put("POS Invoice", name, docstatus=1, is_return=is_return, return_against=against, set_warehouse=store, currency="USD",
                 posting_date="2026-11-08", payments=[{"mode_of_payment": m, "amount": a} for m, a in paid],
                 custom_mpos_tip_amount=round(sum(a for _m, a in chip), 2),
                 custom_pos_invoice_sale_attribute=[{"sale_attribute": k, "attribute_value": v} for k, v in details if v])
