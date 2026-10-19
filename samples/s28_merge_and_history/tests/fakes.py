"""S28's test doubles: a shop held in memory (the record API's answers, as the service's ``Shop`` returns them) and
presses and contexts signed the way the shop signs them."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import time

SAMPLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SAMPLE)
sys.path.insert(0, os.path.join(SAMPLE, "service"))
import app  # noqa: E402
import history  # noqa: E402
import merge  # noqa: E402

ACTION, PAGE = "action-secret", "page-secret"
CONF = {"PP_ACTION_SECRET": ACTION, "PP_PAGE_SECRET": PAGE}


def count(name, *rows, docstatus=0, company="Demo Retail", purpose="Stock Reconciliation", date="2026-10-16",
          time_="10:00:00", store="Store 1 - DR"):
    return {"name": name, "docstatus": docstatus, "company": company, "purpose": purpose, "posting_date": date,
            "posting_time": time_, "set_warehouse": store, "expense_account": "Stock Adjustment - DR",
            "items": [dict(r) for r in rows]}


def row(item, qty, rate=10, wh="Store 1 - DR", **kw):
    return {"item_code": item, "warehouse": wh, "qty": qty, "valuation_rate": rate, **kw}


class FakeShop:
    def __init__(self, counts=(), settings=None, sales=(), users=None):
        self.counts = {c["name"]: json.loads(json.dumps(c)) for c in counts}
        self.settings_row = settings
        self.made, self.notes, self.reads = [], {}, []
        self.sales_rows = {s["name"]: json.loads(json.dumps(s)) for s in sales}
        self.users = users or {}
        self.fail_after_create = False

    def count(self, name):
        if name not in self.counts:
            raise app.ShopError("GET -> HTTP 404", 404)
        return json.loads(json.dumps(self.counts[name]))

    def merged_by(self, key):
        hits = [d["name"] for d in self.made if d.get(merge.KEY_FIELD) == key]
        return hits[0] if hits else None

    def create_count(self, doc):
        name = f"MAT-RECO-NEW-{len(self.made) + 1}"
        self.made.append({**doc, "name": name})
        self.counts[name] = {**doc, "name": name}
        if self.fail_after_create:
            self.fail_after_create = False
            raise app.ShopError("POST Comment -> timed out")
        return name

    def comments(self, name):
        return list(self.notes.get(name, []))

    def add_comment(self, name, text):
        self.notes.setdefault(name, []).append(text)

    def settings(self):
        return dict(self.settings_row or {})

    def sales(self, doctype, customer, count):
        self.reads.append((doctype, customer, count))
        rows = [s for s in self.sales_rows.values() if s["doctype"] == doctype and s["customer"] == customer
                and s["docstatus"] == 1]     # roll-ups included: the page's own check must drop them
        rows.sort(key=lambda s: (s["posting_date"], s.get("posting_time", "")), reverse=True)
        return [{k: s.get(k) for k in ("name", "customer", "docstatus", "posting_date", "posting_time", "is_consolidated")}
                for s in rows[:count]]

    def sale(self, doctype, name):
        return json.loads(json.dumps(self.sales_rows[name]))

    def full_names(self, users):
        return {u: self.users[u] for u in users if u in self.users}


def sale(name, customer, date, doctype=history.POS, owner="cashier1@demo.example", discount=0, pct=0, items=None,
         docstatus=1, is_consolidated=0, store="Store 1 - DR", total=100):
    return {"doctype": doctype, "name": name, "customer": customer, "posting_date": date, "posting_time": "12:00:00",
            "docstatus": docstatus, "is_consolidated": is_consolidated, "owner": owner, "set_warehouse": store,
            "currency": "USD", "grand_total": total, "discount_amount": discount, "additional_discount_percentage": pct,
            "items": items or [{"item_code": "EARBUDS", "item_name": "Earbuds", "qty": 1, "discount_amount": 0,
                                "discount_percentage": 0, "warehouse": store}]}


def press_body(names, key="key-0001-abcd"):
    return json.dumps({"point": "desk_action/1",
                       "context": {"v": 1, "action": "a1", "label": "Merge counts", "user": "u@x", "lang": "en",
                                   "inputs": {}, "idempotency_key": key,
                                   "records": [{"doctype": merge.COUNT, "name": n, "fields": {"name": n}} for n in names]}},
                      sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=ACTION, ts=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}


def context(customer=None, desk=None, nonce="n" * 32, exp_in=300, secret=PAGE):
    now = int(time.time())
    p = {"v": 1, "page": "p1", "nonce": nonce, "iat": now, "exp": now + exp_in, "lang": "en",
         "theme": {"mode": "light", "vars": {}}}
    if desk:
        p.update(doctype=desk[0], name=desk[1])
    else:
        p.update(store="Store 1 - DR", pos_profile="Store 1 — R1",
                 sale={"sale_ref": "s1", "customer": customer, "operator": "cashier1@demo.example", "lines": []})
    return history.sign_context(secret, p)
