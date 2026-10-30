"""A stand-in for one retailer's record API, as S61's service uses it: the payout, the consignor's share, the items, the
till sales' and Desk invoices' lines and headers, the payouts' lines, and the payout lock. Reads honour the filters the
service sends (=, !=, in) and a table's ``parent``; a write carrying a stale ``modified`` is refused as the site does.
"""

from __future__ import annotations

import copy

import consign


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
    raise AssertionError(f"filter {op} not in the stand-in")


class FakeShop:
    def __init__(self):
        self.payouts: dict[str, dict] = {}
        self.consignors: dict[str, dict] = {}
        self.items: list[dict] = []
        self.lines = {"POS Invoice": [], "Sales Invoice": []}
        self.heads = {"POS Invoice": [], "Sales Invoice": []}
        self.rules = [{"name": "R1", "rule_name": consign.LOCK_RULE, "enabled": 1, "mode": "refuse"}]
        self.writes: list[tuple[str, str, dict]] = []
        self.reads: list[tuple] = []
        self.refuse = None            # (status, kind) to raise on every call, as the site refusing the app's user
        self._t = 0

    # the records a test makes
    def payout(self, name, consignor="C1", company="Shop Co", up_to="2026-10-31", state=None, lines=(), **kw):
        self.payouts[name] = dict({"name": name, "consignor": consignor, "company": company, "up_to": up_to,
                                   "workflow_state": state or consign.DRAFT, "modified": f"m-{name}-0",
                                   "lines": [dict(dict({"sale_row": str(r.get("sale_line", "")).split("/")[0]}, **r), parent=name)
                                             for r in lines], "currency": "USD"}, **kw)
        return self.payouts[name]

    def sale(self, typ, name, lines, company="Shop Co", day="2026-10-10", docstatus=1, is_return=0, consolidated=0):
        self.heads[typ].append({"name": name, "docstatus": docstatus, "company": company, "posting_date": day,
                                "is_return": is_return, "is_consolidated": consolidated})
        for i, (row, item, amount) in enumerate(lines):
            self.lines[typ].append({"name": row, "parent": name, "item_code": item, "item_name": item.title(),
                                    "qty": -1 if is_return else 1, "base_net_amount": amount})

    # the record API
    def _tick(self):
        if self.refuse:
            from app import TenantError
            raise TenantError("refused", *self.refuse)

    def doc(self, doctype, name, timeout=None):
        self._tick()
        self.reads.append(("doc", doctype, name))
        if doctype != consign.PAYOUT or name not in self.payouts:
            from app import TenantError
            raise TenantError("not found", 404)
        return copy.deepcopy(self.payouts[name])

    def rows(self, doctype, fields, filters, parent=None, timeout=None):
        self._tick()
        self.reads.append(("rows", doctype, tuple(fields), parent))
        if doctype == consign.CONSIGNOR:
            src = [dict(v, name=k) for k, v in self.consignors.items()]
        elif doctype == "Item":
            src = self.items
        elif doctype in ("POS Invoice Item", "Sales Invoice Item"):
            assert parent == doctype[:-5], parent
            src = self.lines[doctype[:-5]]
        elif doctype in self.heads:
            src = self.heads[doctype]
        elif doctype == consign.LINE:
            assert parent == consign.PAYOUT
            src = [r for p in self.payouts.values() for r in p["lines"]]
        elif doctype == consign.PAYOUT:
            src = list(self.payouts.values())
        elif doctype == "PP CSG Payout Line" or doctype == consign.LINE:
            src = [r for p in self.payouts.values() for r in p["lines"]]
        elif doctype == "Retail Save Rule":
            src = self.rules
        else:
            raise AssertionError(doctype)
        out = [r for r in src if all(_match(r, f) for f in filters)]
        return [{k: r.get(k) for k in fields} for r in copy.deepcopy(out)]

    def update(self, doctype, name, body):
        self._tick()
        p = self.payouts[name]
        if "modified" in body and body["modified"] != p["modified"]:   # the site checks only a sent one
            from app import TenantError
            raise TenantError("stale", 417, "TimestampMismatchError")
        body = {k: v for k, v in body.items() if k != "modified"}
        self.writes.append((doctype, name, copy.deepcopy(body)))
        if "lines" in body:
            body["lines"] = [dict(r, parent=name) for r in body["lines"]]
        p.update(body)
        self._t += 1
        p["modified"] = f"m-{name}-{self._t}"
        return copy.deepcopy(p)
