"""A stand-in for the shop's record API, enough for S45's service: the settings with the shop's ``modified`` check,
till sales and their lines (read through their record type), items and recipes, the app's issues, the shop's stock
(a Material Issue refused for want of stock, as the shop refuses one when negative stock is off), the stock ledger,
counts and food cost records. It is the shop as S45 reads it, never the shop's own rules beyond these."""

import copy
import itertools

import app

CO = "Café Co"
STORE = "Café - CC"


def settings(**kw):
    return dict({"name": CO, "company": CO, "start_from": "2026-10-20 00:00:00", "days_back": 7, "kitchen_store": None,
                 "run_started": "", "modified": "2026-10-20 09:00:00.000001",
                 "day_parts": [{"day_part": "Lunch", "from_time": "11:00:00", "to_time": "16:00:00"}],
                 "allergens": "Milk\nEggs\nCereals containing gluten\nSesame"}, **kw)


ITEMS = {
    "BUN": {"is_stock_item": 1, "stock_uom": "Nos", "pp_rbo_allergens": "Cereals containing gluten, Sesame"},
    "PATTY": {"is_stock_item": 1, "stock_uom": "Nos"},
    "MILK": {"is_stock_item": 1, "stock_uom": "Litre", "pp_rbo_allergens": "Milk"},
    "BEANS": {"is_stock_item": 1, "stock_uom": "Kg"},
    "SODA": {"is_stock_item": 1, "stock_uom": "Nos"},
    "BURGER": {"is_stock_item": 0, "default_bom": "BOM-BURGER", "pp_rbo_allergens": "Cereals containing gluten"},
    "COFFEE": {"is_stock_item": 0, "default_bom": "BOM-COFFEE", "pp_rbo_allergens": "Milk, Diary"},
    "SALAD": {"is_stock_item": 0},
}
BOMS = {
    "BOM-BURGER": {"docstatus": 1, "is_active": 1, "quantity": 1,
                   "items": [{"item_code": "BUN", "stock_qty": 1}, {"item_code": "PATTY", "stock_qty": 1}]},
    "BOM-COFFEE": {"docstatus": 1, "is_active": 1, "quantity": 1,
                   "items": [{"item_code": "BEANS", "stock_qty": 0.018}, {"item_code": "MILK", "stock_qty": 0.15}]},
}


class FakeTenant:
    def __init__(self, sales=None, stock=None, settings_=None, refuse=None, stale_lock=0, lose_answer=0,
                 refuse_entry=None):
        self.settings = {CO: settings_ or settings()}
        self.sales = sales if sales is not None else [
            {"name": "S1", "posting_date": "2026-10-22", "posting_time": "12:00:00", "owner": "ana@x",
             "set_warehouse": STORE, "pos_profile": "Café", "company": CO, "docstatus": 1,
             "items": [{"item_code": "BURGER", "qty": 2, "stock_qty": 2, "net_amount": 160}]},
            {"name": "S2", "posting_date": "2026-10-22", "posting_time": "12:30:00", "owner": "ben@x",
             "pos_profile": "Café", "company": CO, "docstatus": 1,
             "items": [{"item_code": "COFFEE", "qty": 1, "stock_qty": 1, "net_amount": 27}]}]
        self.items, self.boms = copy.deepcopy(ITEMS), copy.deepcopy(BOMS)
        self.stock = dict(stock if stock is not None else {"BUN": 20, "PATTY": 20, "MILK": 5, "BEANS": 1})
        self.issues, self.entries, self.foodcosts, self.checks = {}, {}, {}, {}
        self.ledger, self.recos = [], {}
        self.refuse, self.stale_lock, self.lose_answer, self.refuse_entry = refuse, stale_lock, lose_answer, refuse_entry
        self.n = itertools.count(1)
        self.calls = []

    # ── reads ──
    def _gate(self, what):
        self.calls.append(what)
        if self.refuse and what.startswith(self.refuse[0]):
            raise app.TenantError(f"{what} -> HTTP {self.refuse[1]}", self.refuse[1])

    def doc(self, doctype, name):
        self._gate(f"GET {doctype}")
        if doctype.endswith(" Settings"):
            if name not in self.settings:
                raise app.TenantError("404", 404)
            return copy.deepcopy(self.settings[name])
        if doctype.endswith(" Issue"):
            return copy.deepcopy(self.issues[name])
        if doctype.endswith(" Food Cost"):
            if name not in self.foodcosts:
                raise app.TenantError("404", 404)
            return copy.deepcopy(self.foodcosts[name])
        raise app.TenantError("404", 404)

    def rows(self, doctype, fields, filters, parent=None):
        self._gate(f"LIST {doctype}")
        if doctype == "POS Invoice":
            out = [s for s in self.sales if s["company"] == CO]
            for f, op, v in filters:            # the shop answers only what the filters ask
                if f == "docstatus":
                    out = [s for s in out if s.get("docstatus") == v]
            since = next(v for f, op, v in filters if f == "posting_date")
            return [{k: s.get(k) for k in fields} for s in out if s["posting_date"] >= since]
        if doctype == "POS Invoice Item":
            assert parent == "POS Invoice", "a table is read through its record type"
            names = next(v for f, op, v in filters if f == "parent")
            return [dict(ln, parent=s["name"]) for s in self.sales if s["name"] in names for ln in s["items"]]
        if doctype == "POS Profile":
            return [{"name": "Café", "warehouse": STORE}]
        if doctype == "Item":
            names = next((v for f, op, v in filters if f == "name"), list(self.items))
            return [dict(self.items[n], name=n) for n in names if n in self.items]
        if doctype == "BOM":
            names = next(v for f, op, v in filters if f == "name")
            return [{"name": n, "quantity": b["quantity"], "is_active": b.get("is_active"), "docstatus": b.get("docstatus")}
                    for n, b in self.boms.items() if n in names]
        if doctype == "BOM Item":
            assert parent == "BOM", "a table is read through its record type"
            names = next(v for f, op, v in filters if f == "parent")
            return [dict(r, parent=n) for n, b in self.boms.items() if n in names for r in b["items"]]
        if doctype.endswith(" Issue"):
            out = list(self.issues.values())
            for f, op, v in filters:
                out = [i for i in out if (i.get(f) in v if op == "in" else i.get(f) >= v if op == ">=" else
                                          (v[0] <= i.get(f) <= v[1]) if op == "between" else
                                          bool(i.get(f)) == (v == "set") if op == "is" else i.get(f) == v)]
            return [{k: i.get(k) for k in fields} for i in out]
        if doctype == "Stock Entry":
            out = list(self.entries.values())
            for f, op, v in filters:
                if op == "is":
                    out = [e for e in out if bool(e.get(f)) == (v == "set")]
                elif op == "between":
                    out = [e for e in out if v[0] <= e.get(f) <= v[1]]
                else:
                    out = [e for e in out if e.get(f) == v]
            return [{k: e.get(k) for k in fields} for e in out]
        if doctype == "Bin":
            names = next(v for f, op, v in filters if f == "item_code")
            return [{"item_code": n, "actual_qty": self.stock.get(n, 0)} for n in names if n in self.stock]
        if doctype == "Stock Ledger Entry":
            return copy.deepcopy(self.ledger)
        if doctype == "Stock Reconciliation":
            return [{"name": n} for n in self.recos]
        if doctype == "Stock Reconciliation Item":
            assert parent == "Stock Reconciliation"
            return [r for rows in self.recos.values() for r in rows]
        if doctype.endswith(" Settings"):
            return [copy.deepcopy(s) for s in self.settings.values()]
        raise app.TenantError("403", 403)

    # ── writes ──
    def create(self, doctype, body):
        self._gate(f"POST {doctype}")
        if doctype.endswith(" Allergen Check"):
            name = f"RBO-ALC-{next(self.n):05d}"
            self.checks[name] = dict(copy.deepcopy(body), name=name)
            return {"name": name}
        if doctype.endswith(" Issue"):
            name = f"RBO-ISS-{next(self.n):05d}"
            self.issues[name] = dict(copy.deepcopy(body), name=name, stock_entry=None)
            return {"name": name}
        if doctype == "Stock Entry":
            if self.refuse_entry:
                raise app.TenantError("POST Stock Entry -> HTTP 417", 417, self.refuse_entry[0], self.refuse_entry[1])
            need = {r["item_code"]: r["qty"] for r in body["items"]}
            short = [k for k, v in need.items() if self.stock.get(k, 0) + 1e-9 < v]
            if short:
                raise app.TenantError("POST Stock Entry -> HTTP 417", 417, "NegativeStockError",
                                      f"{short[0]} needed in {body['from_warehouse']}")
            if not body["items"]:
                raise app.TenantError("POST Stock Entry -> HTTP 417", 417, "ValidationError", "Items are required")
            for k, v in need.items():
                self.stock[k] -= v
            name = f"MAT-STE-{next(self.n):05d}"
            self.entries[name] = dict(copy.deepcopy(body), name=name, docstatus=1)
            if self.lose_answer:            # booked, then the answer never came back
                self.lose_answer -= 1
                raise app.TenantError("POST Stock Entry -> TimeoutError")
            return {"name": name}
        raise app.TenantError("403", 403)

    def update(self, doctype, name, body):
        self._gate(f"PUT {doctype}")
        if doctype.endswith(" Settings"):
            s = self.settings[name]
            if self.stale_lock:             # another press stamped the record between our read and our write
                self.stale_lock -= 1
                s.update(run_started="", modified="2026-10-22 10:00:00.999999")
            if "modified" in body and body["modified"] != s["modified"]:
                raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
            s.update({k: v for k, v in body.items() if k != "modified"})
            s["modified"] = f"2026-10-22 10:00:{next(self.n):02d}.000001"
            return copy.deepcopy(s)
        if doctype.endswith(" Issue"):
            self.issues[name].update(body)
            return copy.deepcopy(self.issues[name])
        if doctype.endswith(" Food Cost"):
            f = self.foodcosts[name]
            if body.get("modified") and body["modified"] != f.get("modified"):
                raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
            f.update({k: v for k, v in body.items() if k != "modified"})
            return copy.deepcopy(f)
        raise app.TenantError("403", 403)
