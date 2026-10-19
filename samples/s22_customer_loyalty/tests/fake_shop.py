"""An in-memory stand-in for the shop's record API, for S22's laptop tests. It names records the way the manifest's
record types name them (their unique keys), refuses a second record with the same name (``Duplicate``, as the shop's
409), filters as the record API does for the operators the service uses, and follows the shop's permission rule (a
record type runs on its standard rows until the first change copies them into custom rows). ⚠ Not the shop: the test
bench proves the same against a real one."""

from __future__ import annotations

import copy
import itertools
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
from shop import Duplicate, ShopError  # noqa: E402

NAMED_BY = {"PP LYL Ledger": "source_key", "PP LYL Balance": "balance_key", "PP LYL Member": "customer", "PP LYL Plan": "plan_name",
            "PP LYL Settings": "title", "Role": "role_name", "User": "email", "Customer Group": "customer_group_name",
            "Workflow": "workflow_name", "Workflow State": "workflow_state_name",
            "Workflow Action Master": "workflow_action_name", "Promotion Bonus Buys Master": "id"}
RIGHTS = ("read", "write", "create", "delete", "submit", "cancel", "amend", "report", "export", "import", "share",
          "print", "email")
STANDARD = {"Purchase Receipt": [("Stock User", "read write create submit"),
                                 ("Stock Manager", "read write create submit cancel"),
                                 ("Purchase User", "read write create submit")]}
PM = ("get_role_permissions", "add_role_permission", "update_role_permission", "reset_role_permissions")


def row(dt, role, rights, level=0):
    return {"parent": dt, "role": role, "permlevel": level, "if_owner": 0, **{r: int(r in rights.split()) for r in RIGHTS}}


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
    if op == "like":                       # the wallet's refunds of one payment: a prefix ending in %
        return str(v).startswith(val.rstrip("%")) if val.endswith("%") and "%" not in val[:-1] else v == val
    return {"<": v < val, "<=": v <= val, ">": v > val, ">=": v >= val}[op]


class FakeShop:
    def __init__(self):
        self.db, self.calls, self.custom = {}, [], {}
        self._seq = itertools.count(1)
        self.fail_after_insert = None

    def put(self, dt, name, **fields):
        self.db.setdefault(dt, {})[name] = dict(fields, name=name, doctype=dt)
        return self.db[dt][name]

    def get(self, dt, name):
        d = self.db.get(dt, {}).get(name)
        return copy.deepcopy(d) if d else None

    def list(self, dt, filters=None, fields=("name",), order_by="", limit=0):
        if dt == "Custom DocPerm":
            parent = dict((f[0], f[2]) for f in filters)["parent"]
            return [dict(r, name=f"{parent}-{i}") for i, r in enumerate(self.custom.get(parent, []))]
        rows = [d for d in self.db.get(dt, {}).values() if all(_match(d, f) for f in filters or [])]
        if order_by.startswith("rank"):
            rows.sort(key=lambda d: d.get("rank") or 0)
        elif order_by.endswith(" desc"):
            rows.sort(key=lambda d: str(d.get(order_by.split()[0]) or ""), reverse=True)
        out = [{k: d.get(k) for k in set(fields) | {"name"}} for d in rows]
        return out[:limit] if limit else out

    def insert(self, doc):
        dt = doc["doctype"]
        if dt == "Custom DocPerm":
            self.custom.setdefault(doc["parent"], []).append({k: doc[k] for k in ("parent", "role", "permlevel", "if_owner", *RIGHTS)})
            return "x"
        name = doc.get(NAMED_BY.get(dt, "")) or doc.get("name") or f"{dt[:3].upper()}-{next(self._seq):05d}"
        if name in self.db.get(dt, {}):
            raise Duplicate(409, f"{dt} {name} already exists")
        self.db.setdefault(dt, {})[name] = dict(copy.deepcopy(doc), name=name)
        if dt == "Workflow":
            self.db.setdefault("Custom Field", {}).setdefault(f"{doc['document_type']}-workflow_state", {"name": "x"})
        self.calls.append(("insert", dt, name))
        if self.fail_after_insert == dt:
            self.fail_after_insert = None
            raise SystemExit("CRASH (injected) after the shop wrote the row")
        return name

    def update(self, dt, name, fields):
        if name not in self.db.get(dt, {}):
            raise ShopError(404, f"{dt} {name} not found")
        self.db[dt][name].update(copy.deepcopy(fields))
        return self.db[dt][name]

    def delete(self, dt, name):
        if dt == "Customer Group" and any(c.get("customer_group") == name for c in self.db.get("Customer", {}).values()):
            raise ShopError(417, "LinkExists")
        if name in getattr(self, "linked", ()):
            raise ShopError(417, "LinkExists: linked with Workflow Action")
        del self.db[dt][name]

    def effective(self, dt):
        return self.custom[dt] if dt in self.custom else [row(dt, r, x) for r, x in STANDARD.get(dt, [])]

    def method(self, dotted, body=None):
        self.calls.append(("method", dotted))
        if dotted.startswith("ivendnext_mpos.api.v1.") and dotted.rsplit(".", 1)[-1] in PM:
            dt = body.get("doctype") or body.get("parent")
            if dotted.endswith("get_role_permissions"):
                return copy.deepcopy(self.effective(dt))
            if dotted.endswith("reset_role_permissions"):
                self.custom.pop(dt, None)
                return None
            self.custom.setdefault(dt, copy.deepcopy(self.effective(dt)))
            if dotted.endswith("add_role_permission"):
                self.custom[dt].append(row(dt, body["role"], ""))
            else:
                for r in self.custom[dt]:
                    if r["role"] == body["role"] and r["permlevel"] == body["permlevel"]:
                        r[body["ptype"]] = body["value"]
            return None
        if dotted == "ivendnext_mpos.api.v1.generate_keys":
            return {"api_secret": "new"}
        if dotted == "ivendnext_mpos.api.v1.apply_workflow":
            d = self.db["Purchase Receipt"][json.loads(body["doc"])["name"]]
            d.update(workflow_state="PP LYL Verified", docstatus=1)
            return d
        if dotted == "ivendnext_mpos.api.v1.add_comment":
            return self.put("Comment", f"c{len(self.calls)}", **body)
        raise KeyError(dotted)


def shop(return_days=14) -> FakeShop:
    t = FakeShop()
    t.put("PP LYL Settings", "Default", default_plan="Bronze", return_days=return_days, tier_window_days=365,
          currency_precision=2, currency="USD", walk_in_customers="Walk-in — Demo Retail")
    for name, rank, thr, disc in (("Bronze", 1, 0, 0), ("Silver", 2, 1000, 3), ("Gold", 3, 2500, 5)):
        t.put("PP LYL Plan", name, customer_group=f"PP LYL {name}", rank=rank, spend_threshold=thr,
              discount_percent=disc, cash_back_percent=2, active=1)
    t.put("Customer", "Walk-in — Demo Retail", customer_group="Individual")
    t.put("Customer", "C1", customer_group="Individual")
    return t


def sale(t, name, customer, grand_total, posting_date="2026-10-01", is_return=0, return_against=None):
    return t.put("POS Invoice", name, customer=customer, grand_total=grand_total, posting_date=posting_date,
                 is_return=is_return, return_against=return_against, docstatus=1)
