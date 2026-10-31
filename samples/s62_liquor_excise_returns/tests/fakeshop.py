"""A stand-in for one retailer's record API, as S62's service uses it: the return, the duty classes, the items, the stock
ledger and the Stock Entries. The ledger keeps its balances as the site's does: rows ordered by ``posting_datetime`` then
``creation``, each row's ``qty_after_transaction`` its item's balance in its warehouse after it, and a stock count
(Stock Reconciliation of an item without batches) written with ``actual_qty`` 0 and the counted balance. Reads honour the
filters the service sends (=, !=, <, >, >=, in, not in, is set) and add up with ``group_by`` (``sum(f) as a``,
``max(f) as a``) as the site's list API does; a write carrying a stale ``modified`` is refused as the site does.
"""

from __future__ import annotations

import copy
import re

import exr

AGG = re.compile(r"^(sum|max)\((\w+)\) as (\w+)$")


class Refused(Exception):
    pass


def _match(row: dict, flt) -> bool:
    f, op, v = flt[-3:]
    got = row.get(f)
    if op == "=":
        return got == v
    if op == "!=":
        return got != v
    if op == "in":
        return got in v
    if op == "not in":
        return got not in v
    if op == "is":
        assert v == "set", v
        return got not in (None, "")
    if op in ("<", ">", ">="):
        if got is None:
            return False
        return {"<": got < v, ">": got > v, ">=": got >= v}[op]
    raise AssertionError(f"filter {op} not in the stand-in")


class FakeShop:
    def __init__(self):
        self.returns: dict[str, dict] = {}
        self.classes: list[dict] = []
        self.items: list[dict] = []
        self.ledger: list[dict] = []
        self.entries: dict[str, str] = {}      # Stock Entry name -> purpose
        self.rules = [{"name": "R1", "rule_name": exr.LOCK_RULE, "enabled": 1, "mode": "refuse"}]
        self.writes: list[tuple[str, str, dict]] = []
        self.reads: list[tuple] = []
        self.refuse = None            # (status, kind) to raise on every call, as the site refusing the app's user
        self.fail_on = None           # a doctype whose read fails with (status, kind)
        self._t = 0
        self._n = 0

    # the records a test makes
    def ret(self, name, store="Store A", company="Shop Co", start="2026-10-01", end="2026-10-31", unit="Litres", state=None,
            **kw):
        self.returns[name] = dict({"name": name, "store": store, "company": company, "from_date": start, "to_date": end,
                                   "unit": unit, "workflow_state": state or exr.DRAFT, "modified": f"m-{name}-0",
                                   "lines": []}, **kw)
        return self.returns[name]

    def move(self, item, when, vtype, vno, qty, store="Store A", cancelled=0):
        """A ledger row moving ``qty`` (signed) of ``item`` in ``store`` at ``when``; balances follow."""
        self._n += 1
        self.ledger.append({"name": f"SLE-{self._n:05d}", "item_code": item, "warehouse": store, "posting_datetime": when,
                            "creation": f"{when}.{self._n:06d}", "voucher_type": vtype, "voucher_no": vno,
                            "actual_qty": float(qty), "is_cancelled": cancelled, "count_to": None})
        self._balances()

    def count(self, item, when, counted, store="Store A", vno="SR-1"):
        """A stock count of an item without batches: ``actual_qty`` 0, the balance set to ``counted``."""
        self.move(item, when, "Stock Reconciliation", vno, 0, store)
        self.ledger[-1]["count_to"] = float(counted)
        self._balances()

    def entry(self, name, purpose):
        self.entries[name] = purpose

    def _balances(self):
        bal: dict[tuple, float] = {}
        for r in sorted(self.ledger, key=lambda r: (r["posting_datetime"], r["creation"])):
            if r["is_cancelled"]:
                continue
            k = (r["item_code"], r["warehouse"])
            bal[k] = r["count_to"] if r["count_to"] is not None else bal.get(k, 0.0) + r["actual_qty"]
            r["qty_after_transaction"] = bal[k]

    # the record API
    def _tick(self, doctype=None):
        from app import TenantError
        if self.refuse:
            raise TenantError("refused", *self.refuse)
        if self.fail_on and doctype == self.fail_on[0]:
            raise TenantError("refused", *self.fail_on[1:])

    def doc(self, doctype, name, timeout=None):
        self._tick(doctype)
        self.reads.append(("doc", doctype, name))
        if doctype != exr.RETURN or name not in self.returns:
            from app import TenantError
            raise TenantError("not found", 404)
        return copy.deepcopy(self.returns[name])

    def rows(self, doctype, fields, filters, group_by=None, timeout=None):
        self._tick(doctype)
        self.reads.append(("rows", doctype, tuple(fields), group_by))
        if doctype == exr.CLASS:
            src = self.classes
        elif doctype == "Item":
            src = self.items
        elif doctype == "Stock Ledger Entry":
            src = self.ledger
        elif doctype == "Stock Entry":
            src = [{"name": k, "purpose": v} for k, v in self.entries.items()]
        elif doctype == exr.RETURN:
            src = list(self.returns.values())
        elif doctype == "Retail Save Rule":
            src = self.rules
        else:
            raise AssertionError(doctype)
        out = [r for r in src if all(_match(r, f) for f in filters)]
        if not group_by:
            for f in fields:
                assert not AGG.match(f), f"{f} without group_by"
            return [{k: r.get(k) for k in fields} for r in copy.deepcopy(out)]
        keys = [k.strip() for k in group_by.split(",")]
        assert [f for f in fields if not AGG.match(f)] == keys, (fields, keys)
        groups: dict[tuple, list] = {}
        for r in out:
            groups.setdefault(tuple(r.get(k) for k in keys), []).append(r)
        res = []
        for key, rs in groups.items():
            row = dict(zip(keys, key))
            for f in fields:
                m = AGG.match(f)
                if m:
                    fn, col, alias = m.groups()
                    vals = [r.get(col) for r in rs]
                    row[alias] = sum(vals) if fn == "sum" else max(vals)
            res.append(row)
        return res

    def update(self, doctype, name, body):
        self._tick(doctype)
        p = self.returns[name]
        if "modified" in body and body["modified"] != p["modified"]:   # the site checks only a sent one
            from app import TenantError
            raise TenantError("stale", 417, "TimestampMismatchError")
        body = {k: v for k, v in body.items() if k != "modified"}
        self.writes.append((doctype, name, copy.deepcopy(body)))
        p.update(body)
        self._t += 1
        p["modified"] = f"m-{name}-{self._t}"
        return copy.deepcopy(p)
