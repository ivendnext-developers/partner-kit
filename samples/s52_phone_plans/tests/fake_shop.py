"""An in-memory stand-in for one retailer's record API, for S52's laptop tests: it names records the way the manifest's
record types name them (their unique keys), refuses a second record with the same name (``Duplicate``, as the
retailer's 409), and filters for the operators the service uses. It counts the reads, so a test can tell which
retailer was read. Not the retailer: the programme's test bench proves the same against a real one.
"""

from __future__ import annotations

import copy
import itertools
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
from shop import Duplicate, ShopError  # noqa: E402

NAMED_BY = {"PP TEL Activation": "activation_key", "PP TEL Settings": "title"}


def _match(doc, f) -> bool:
    field, op, val = f
    v = doc.get(field)
    return v == val if op == "=" else v in val if op == "in" else False


class FakeShop:
    def __init__(self, url: str):
        self.url, self.db, self.reads, self.lock = url, {}, 0, threading.Lock()
        self._seq = itertools.count(1)

    def put(self, dt, name, **fields):
        self.db.setdefault(dt, {})[name] = dict(fields, name=name, doctype=dt)
        return self.db[dt][name]

    def get(self, dt, name):
        with self.lock:
            self.reads += 1
            d = self.db.get(dt, {}).get(name)
            return copy.deepcopy(d) if d else None

    def list(self, dt, filters=None, fields=("name",), order_by="", limit=0):
        with self.lock:
            rows = [d for d in self.db.get(dt, {}).values() if all(_match(d, f) for f in filters or [])]
            return [{k: d.get(k) for k in set(fields) | {"name"}} for d in rows]

    def insert(self, doc):
        with self.lock:
            dt = doc["doctype"]
            if dt == "Item Price" and doc["item_code"] not in self.db.get("Item", {}):
                raise ShopError(417, "Item not found")
            name = doc.get(NAMED_BY.get(dt, "")) or f"{dt[:3].upper()}-{next(self._seq):05d}"
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


def retailer(url: str, account: str, key: str) -> FakeShop:
    t = FakeShop(url)
    t.put("PP TEL Settings", "Default", title="Default", telecom_account=account, telecom_key=key,
          plan_item_group="Mobile Plans", price_list="Standard Selling",
          walk_in_customers="Walk-in Customer\n")
    for code in ("PP-TEL-S", "PP-TEL-M", "PP-TEL-L"):
        t.put("Item", code, item_group="Mobile Plans")
    for code in ("PP-TEL-PHONE-X1", "PP-TEL-PHONE-X2"):
        t.put("Item", code, item_group="Phones")
    return t


def paid_sale(t: FakeShop, name: str, plan="PP-TEL-S", phone="PP-TEL-PHONE-X1", customer="CUST-1", serial="IMEI-1",
              phones=1, plans=None):
    items = [{"idx": 1, "item_code": phone, "item_group": "Phones", "qty": phones, "serial_no": serial}]
    for i, p in enumerate(plans or [plan]):
        items.append({"idx": 2 + i, "item_code": p, "item_group": "Mobile Plans", "qty": 1, "serial_no": ""})
    return t.put("POS Invoice", name, docstatus=1, is_return=0, customer=customer, items=items)


class FakeFeed:
    """The event feed's door, in memory: events stay until ``done``; ``failed`` keeps them for the next poll."""

    def __init__(self, events):
        self.events_, self.notes = list(events), {}

    def events(self, limit=100, page=None):
        return list(self.events_), None, None

    def done(self, ids):
        before = len(self.events_)
        self.events_ = [e for e in self.events_ if e["id"] not in ids]
        return before - len(self.events_)

    def failed(self, id_, note):
        self.notes[id_] = note

    def backlog(self):
        return len(self.events_)
