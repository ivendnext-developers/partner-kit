"""An in-memory stand-in for the shop's record API, for S25's laptop tests. Adapted from S22's
(``samples/s22_customer_loyalty/tests/fake_shop.py`` @ 3546aaf; a defect there may be a defect here). It names records the
way the shop does (the Card by its key, a Gift Card by its number, a Gift Card Balance by the engine's ``GC-BAL-`` series),
refuses a second record with the same name (``Duplicate``, as the shop's 409), stamps ``creation`` in the shop's own
local time, and does what the ENGINE does on a submitted Gift Card Balance: it SETS the card's balance
(``ivendnext_pos`` ``doctype/gift_card_balance/gift_card_balance.py``, at the bench's engine pin ``2548b757``).
⚠ Not the shop: the test bench proves the same against a real one."""

from __future__ import annotations

import copy
import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
from shop import Duplicate, ShopError  # noqa: E402

NAMED_BY = {"PP GCS Card": "card_key", "PP GCS Settings": "title", "Gift Card": "serial_number"}
SHOP_NOW = "2026-10-15 10:00:00.123456"       # the shop's own clock (local time), stamped on every new record


def _match(doc, f) -> bool:
    field, op, val = f
    v = doc.get(field)
    if op == "=":
        return v == val
    if op == "!=":
        return v != val
    if op == "in":
        return v in val
    if v is None:
        return False
    return {"<": v < val, "<=": v <= val, ">": v > val, ">=": v >= val}[op]


class FakeShop:
    def __init__(self):
        self.db, self.calls = {}, []
        self._seq = itertools.count(1)
        self.fail_after_insert = None
        self.redeemed = set()                # card numbers a POS payment row names (the till's "redeemed")
        self.now = SHOP_NOW

    def put(self, dt, name, **fields):
        self.db.setdefault(dt, {})[name] = dict(fields, name=name, doctype=dt)
        return self.db[dt][name]

    def get(self, dt, name):
        d = self.db.get(dt, {}).get(name)
        return copy.deepcopy(d) if d else None

    def list(self, dt, filters=None, fields=("name",), order_by="", limit=0):
        rows = [d for d in self.db.get(dt, {}).values() if all(_match(d, f) for f in filters or [])]
        if order_by:
            key = order_by.split()[0]
            rows.sort(key=lambda d: str(d.get(key) or ""), reverse=order_by.endswith("desc"))
        out = [{k: d.get(k) for k in set(fields) | {"name"}} for d in rows]
        return out[:limit] if limit else out

    def insert(self, doc):
        dt = doc["doctype"]
        if dt == "Gift Card Balance":
            name = f"GC-BAL-10-26-{next(self._seq):05d}"
        else:
            name = doc.get(NAMED_BY.get(dt, "")) or doc.get("name") or f"{dt[:3].upper()}-{next(self._seq):05d}"
        if name in self.db.get(dt, {}):
            raise Duplicate(409, f"{dt} {name} already exists")
        self.db.setdefault(dt, {})[name] = dict(copy.deepcopy(doc), name=name, creation=self.now)
        if dt == "Gift Card Balance" and int(doc.get("docstatus") or 0) == 1:
            self.db["Gift Card"][doc["gift_card"]]["balance"] = float(doc["balance"])     # the engine's on_submit
        self.calls.append(("insert", dt, name))
        if self.fail_after_insert == dt:
            self.fail_after_insert = None
            raise SystemExit("CRASH (injected) after the shop wrote the row")
        return name

    def update(self, dt, name, fields):
        if name not in self.db.get(dt, {}):
            raise ShopError(404, f"{dt} {name} not found")
        self.db[dt][name].update(copy.deepcopy(fields))
        self.calls.append(("update", dt, name))
        return self.db[dt][name]

    def method(self, dotted, body=None):
        self.calls.append(("method", dotted))
        if dotted == "ivendnext_pos.api.pos_invoice.get_gift_card_status":
            n = body["gift_card_no"]
            gc = self.db.get("Gift Card", {}).get(n) or {}
            return {"name": gc.get("name"), "balance": gc.get("balance"), "redeemed": n in self.redeemed}
        raise KeyError(dotted)

    # what the tests read
    def balance_entries(self, number):
        return [d for d in self.db.get("Gift Card Balance", {}).values() if d["gift_card"] == number]

    def card(self, key):
        return self.db["PP GCS Card"][key]


SETTINGS = dict(title="Default", enabled=1, currency="ZAR", currency_precision=2, threshold=1000, card_value=100,
                card_item="PROMO-GIFT", max_cards_per_sale=1, hold_hours=24, walk_in_customers="Walk-in — Demo",
                excluded_customer_groups="Staff\nAccount Customers")
ITEM = dict(custom_is_gift_card=1, disabled=0, custom_recharge=0, custom_cashback=0, custom_use_as_store_credit=0,
            custom_expiry_days=0)


def shop(item=None, **settings) -> FakeShop:
    t = FakeShop()
    t.put("PP GCS Settings", "Default", **dict(SETTINGS, **settings))
    t.put("Item", "PROMO-GIFT", **dict(ITEM, **(item or {})))
    t.put("Customer", "Walk-in — Demo", customer_group="Individual")
    t.put("Customer", "C1", customer_group="Individual", email_id="c1@example.com")
    t.put("Customer", "C2", customer_group="Individual", email_id=None)
    t.put("Customer", "STAFF1", customer_group="Staff")
    return t


def sale(t, name, customer="C1", grand_total=1200, items=None, payments=None, is_return=0, return_against=None,
         transaction_mode="Sale", currency="ZAR", docstatus=1, **extra):
    items = items if items is not None else [{"item_code": "X", "amount": grand_total, "transaction_mode": "Sale"}]
    payments = payments if payments is not None else [{"type": "Cash", "amount": grand_total}]
    if is_return and transaction_mode == "Sale":        # the till's return, as the engine composes it (make_return_doc)
        transaction_mode = "Sale Return"
        items = [dict(i, transaction_mode="Sale Return") for i in items]
    return t.put("POS Invoice", name, customer=customer, customer_name=f"{customer} name", grand_total=grand_total,
                 items=items, payments=payments, is_return=is_return, return_against=return_against,
                 transaction_mode=transaction_mode, currency=currency, docstatus=docstatus, **extra)
