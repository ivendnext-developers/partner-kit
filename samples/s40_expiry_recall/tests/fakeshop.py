"""S40's stand-in shop: the record API the service reads and writes (lots, items, bundles and their lot rows, sales
documents, the app's own records), the v1 lot read, and calls signed exactly as the shop signs them (base64
HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON). Used by every test file."""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service")]
import app  # noqa: E402
import recall  # noqa: E402

NOW = datetime.datetime(2026, 10, 22, 6, 0, tzinfo=datetime.timezone.utc).timestamp()   # 09:00 in Nairobi
TODAY = datetime.date(2026, 10, 22)
SECRETS = {"block": "s40-block", "worklist": "s40-worklist", "receipt": "s40-receipt", "disposal": "s40-disposal",
           "count": "s40-count"}
DISP, FRONT, QUAR = "Dispensary - ICG", "Front - ICG", "Quarantine - ICG"
STAMP = "2026-10-20 10:00:00.000001"


def day(n: int) -> str:
    return (TODAY + datetime.timedelta(days=n)).isoformat()


def settings():
    return {"hours_from_utc": 3, "min_shelf_days": 180, "supplier_note_required": 1, "erp_users": "sap@shop\n",
            "near_expiry_days": 90, "quarantine_stores": QUAR + "\nQuarantine 2 - ICG", "pack_expiry_required": 1,
            "class_1_start_hours": 24, "class_1_days": 14, "class_1_depth": "Consumer",
            "class_2_start_hours": 72, "class_2_days": 21, "class_2_depth": "Retail",
            "class_3_start_hours": 120, "class_3_days": 28, "class_3_depth": "Wholesale",
            "witness_rule": "Items with a listed schedule", "witness_schedules": "", "schedule_field": "pp_rxc_schedules"}


def lots():
    """AMOX-A recalled with stock in two stores and three sales; AMOX-B already disabled; AMOX-N no expiry; PARA-A near
    expiry; PARA-B fresh; TRAM-X expired; TRAM-A fresh."""
    return {"AMOX-A": {"item": "AMOX", "expiry_date": day(400), "manufacturing_date": day(-300), "disabled": 0, "batch_qty": 34},
            "AMOX-B": {"item": "AMOX", "expiry_date": day(500), "manufacturing_date": day(-200), "disabled": 1, "batch_qty": 0},
            "AMOX-N": {"item": "AMOX", "expiry_date": None, "manufacturing_date": day(-30), "disabled": 0, "batch_qty": 5},
            "PARA-A": {"item": "PARA", "expiry_date": day(30), "manufacturing_date": day(-700), "disabled": 0, "batch_qty": 20},
            "PARA-B": {"item": "PARA", "expiry_date": day(600), "manufacturing_date": day(-100), "disabled": 0, "batch_qty": 50},
            "TRAM-X": {"item": "TRAM", "expiry_date": day(-3), "manufacturing_date": day(-700), "disabled": 0, "batch_qty": 4},
            "TRAM-A": {"item": "TRAM", "expiry_date": day(300), "manufacturing_date": day(-60), "disabled": 0, "batch_qty": 10},
            "SOAP-N": {"item": "SOAP", "expiry_date": None, "manufacturing_date": None, "disabled": 0, "batch_qty": 9}}


def items():
    return {"AMOX": {"has_expiry_date": 1, "shelf_life_in_days": 730, "item_group": "Prescription Medicines",
                     "pp_rxc_schedules": [{"schedule": "POM", "effective_from": day(-900)}]},
            "PARA": {"has_expiry_date": 1, "shelf_life_in_days": 0, "item_group": "Over-the-Counter Medicines",
                     "pp_rxc_schedules": []},
            "TRAM": {"has_expiry_date": 1, "shelf_life_in_days": 0, "item_group": "Controlled Medicines",
                     "pp_rxc_schedules": [{"schedule": "CD Schedule 2", "effective_from": day(-900)}]},
            "SOAP": {"has_expiry_date": 0, "shelf_life_in_days": 0, "item_group": "Toiletries", "pp_rxc_schedules": []}}


def bundles():
    """The lot ledger. AMOX-A: 50 in; sold at the dispensary by a till sale whose day closed (its lot record now on the
    day's merged invoice, 3) and a Desk invoice (2), and by a till sale whose day is still open (its lot record on the POS
    sale, 3: it books no stock yet); 10 moved to the front store, 1 delivered there; a cancelled sale."""
    def b(name, vt, vn, wh, entries, **kw):
        return dict({"name": name, "voucher_type": vt, "voucher_no": vn, "warehouse": wh, "docstatus": 1,
                     "is_cancelled": 0, "entries": [{"batch_no": l, "qty": q} for l, q in entries]}, **kw)
    return [b("B1", "Purchase Receipt", "PR-1", DISP, [("AMOX-A", 50), ("AMOX-N", 5)]),
            b("B2", "POS Invoice", "POS-1", DISP, [("AMOX-A", -3)]),
            b("B3", "Sales Invoice", "SI-MERGED", DISP, [("AMOX-A", -3)]),
            b("B4", "Sales Invoice", "SI-2", DISP, [("AMOX-A", -2)]),
            b("B5", "Stock Entry", "STE-1", DISP, [("AMOX-A", -10)]),
            b("B6", "Stock Entry", "STE-1", FRONT, [("AMOX-A", 10)]),
            b("B7", "Delivery Note", "DN-1", FRONT, [("AMOX-A", -1)]),
            b("B8", "Sales Invoice", "SI-3", DISP, [("AMOX-A", -4)], docstatus=2, is_cancelled=1),
            b("B9", "Purchase Receipt", "PR-2", DISP, [("PARA-A", 20), ("PARA-B", 50)]),
            b("B10", "Purchase Receipt", "PR-3", DISP, [("TRAM-X", 4), ("TRAM-A", 10)]),
            b("B11", "Purchase Receipt", "PR-9", DISP, [("PARA-B", 6), ("PARA-A", 4)], docstatus=0)]


SALES_DOCS = {
    "POS Invoice": {"POS-1": {"customer": "CUST-1", "customer_name": "Amina Otieno", "posting_date": day(-5)}},
    "Sales Invoice": {"SI-MERGED": {"customer": "CUST-5", "customer_name": "Daniel Mutua", "posting_date": day(-6),
                                    "is_consolidated": 1},
                      "SI-2": {"customer": "CUST-2", "customer_name": "Brian Kamau", "posting_date": day(-2), "is_consolidated": 0},
                      "SI-3": {"customer": "CUST-3", "customer_name": "Cancelled Sale", "posting_date": day(-1), "is_consolidated": 0}},
    "Delivery Note": {"DN-1": {"customer": "CUST-4", "customer_name": "Westlands Clinic", "posting_date": day(-1)}}}


def _match(row: dict, flt) -> bool:
    if len(flt) == 4:
        flt = flt[1:]
    f, op, v = flt
    x = row.get(f)
    if op == "=":
        return x == v
    if op == "!=":
        return x != v
    if op == "in":
        return x in v
    if op == "<=":
        return x is not None and x <= v
    if op == ">":
        return x is not None and x > v
    if op == "is":
        return (x in (None, "")) if v == "not set" else (x not in (None, ""))
    raise AssertionError(f"the stand-in does not know {op}")


class FakeTenant:
    def __init__(self, settings_=None, refuse=None, stale_lot=None, prefix="pp_rcl"):
        self.settings = settings() if settings_ is None else (None if settings_ is False else settings_)
        self.lots, self.items, self.bundles, self.sales = lots(), items(), bundles(), copy.deepcopy(SALES_DOCS)
        for v in self.lots.values():
            v["modified"] = STAMP
        self.own = {}                   # (record type, name) -> record
        self.refuse, self.stale_lot, self.p = refuse, stale_lot, prefix
        self.writes, self.reads = [], []
        self.entries = []               # submitted stock entries naming a disposal record: rows as the record API lists them
        self.lock_rule_on = True
        self.lock_rule_edit = {}

    def put_own(self, kind: str, name: str, rec: dict):
        self.own[(f"{self.p.upper().replace('_', ' ')} {kind}", name)] = dict(rec, name=name, modified=STAMP)

    def get_own(self, kind: str, name: str) -> dict:
        return self.own[(f"{self.p.upper().replace('_', ' ')} {kind}", name)]

    def _gate(self, what):
        self.reads.append(what)
        if self.refuse:
            raise app.TenantError(f"-> HTTP {self.refuse}", self.refuse)

    def doc(self, doctype, name):
        self._gate(("doc", doctype, name))
        if doctype.endswith(" Settings"):
            if self.settings is None or name != "Default":
                raise app.TenantError("GET -> HTTP 404", 404)
            return dict(self.settings, name="Default")
        if doctype == "Item":
            if name not in self.items:
                raise app.TenantError("GET -> HTTP 404", 404)
            return dict(copy.deepcopy(self.items[name]), name=name)
        if (doctype, name) in self.own:
            return copy.deepcopy(self.own[(doctype, name)])
        raise app.TenantError("GET -> HTTP 404", 404)

    def rows(self, doctype, fields, filters):
        self._gate(("rows", doctype, json.dumps(filters, sort_keys=True)))
        if doctype == "Batch":
            out = [dict(v, name=k) for k, v in self.lots.items()]
        elif doctype == "Item":
            out = [{"name": k, **{f: v.get(f) for f in fields if f != "name"}} for k, v in self.items.items()]
        elif doctype == "Serial and Batch Bundle":
            out = [dict({k: v for k, v in b.items() if k != "entries"}, **e) for b in self.bundles for e in b["entries"]]
        elif doctype in self.sales:
            out = [dict(v, name=k) for k, v in self.sales[doctype].items()]
        elif doctype == "Stock Entry":
            out = [dict(r) for r in self.entries]
        elif doctype == "Retail Save Rule":
            P = self.p.upper().replace('_', ' ')
            out = [dict({"name": "r1", "rule_name": f"{P} disposal locked once the visit is recorded",
                         "enabled": 1 if self.lock_rule_on else 0, "mode": "refuse", "states": f"{P} Visit recorded",
                         "locked_fields": "store\nnotice\nreason\nlines\nofficer_name\nauthority\nofficer_id\nvisit_date\n"
                                          "signed_form\nattested_by\nmethod\nprior_notice_on", "bypass_roles": ""}, **self.lock_rule_edit)]
        elif doctype.endswith("Recall Notice") and any(len(f) == 4 for f in filters):
            out = [dict(lot) for (dt, _), r in self.own.items() if dt == doctype for lot in r.get("lots") or []]
        else:
            out = [copy.deepcopy(r) for (dt, _), r in self.own.items() if dt == doctype]
        for flt in filters:
            out = [r for r in out if _match(r, flt)]
        return copy.deepcopy(out)

    def create(self, doctype, body):
        self._gate(("create", doctype))
        name = f"{body.get('notice')}--{body.get('store')}" if doctype.endswith("Recall Store Progress") else body["name"]
        if (doctype, name) in self.own:
            raise app.TenantError("POST -> HTTP 409", 409, "DuplicateEntryError")
        self.own[(doctype, name)] = dict(body, name=name, modified=STAMP)
        self.writes.append(("create", doctype, name, body))
        return self.own[(doctype, name)]

    def update(self, doctype, name, body):
        self._gate(("update", doctype, name))
        if doctype == "Batch":
            if name == self.stale_lot or body.get("modified") != self.lots[name]["modified"]:
                raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
            self.lots[name].update({k: v for k, v in body.items() if k != "modified"})
            self.lots[name]["modified"] = "2026-10-22 09:00:00.000001"
        else:
            rec = self.own[(doctype, name)]
            if body.get("modified") != rec["modified"]:
                raise app.TenantError("PUT -> HTTP 417", 417, "TimestampMismatchError")
            rec.update({k: v for k, v in body.items() if k != "modified"})
            rec["modified"] = "2026-10-22 09:00:00.000002"
        self.writes.append(("update", doctype, name, body))
        return {}

    def method(self, name, args):
        """``get_batch_qty``: the shop's own lot read — disabled lots left out, expired lots kept (``for_stock_levels``),
        draft and cancelled bundles and POS sales' own bundles never counted."""
        self._gate(("method", name, json.dumps(args, sort_keys=True)))
        assert name == "get_batch_qty" and args.get("for_stock_levels")
        tot = {}
        for b in self.bundles:
            if b["docstatus"] != 1 or b["voucher_type"] == "POS Invoice":
                continue
            if args.get("warehouse") and b["warehouse"] != args["warehouse"]:
                continue
            for e in b["entries"]:
                if self.lots[e["batch_no"]]["disabled"]:
                    continue
                k = (e["batch_no"], b["warehouse"])
                tot[k] = tot.get(k, 0) + e["qty"]
        return [{"batch_no": l, "warehouse": w, "qty": q} for (l, w), q in sorted(tot.items()) if q > 0]


def signed(raw: bytes, secret: str, ts: str | None = None) -> dict:
    ts = ts or str(int(NOW))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    return {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "X-iVendNext-Request-Id": "rq-1"}


def raw_of(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def press_body(record_type: str, name: str, fields: dict, user: str = "officer@shop") -> bytes:
    return raw_of({"point": "desk_action/1", "context": {
        "v": 1, "action": "x", "label": "x", "user": user, "lang": "en", "idempotency_key": "k-1", "inputs": {},
        "records": [{"doctype": record_type, "name": name, "fields": fields}]}})


def check_body(record_type: str, fields: dict, user: str = "receiver@shop") -> bytes:
    return raw_of({"point": "doccheck/1", "context": {
        "v": 1, "company": "iStore", "doctype": record_type, "event": "submit", "name": fields.get("name", "DOC-1"),
        "user": user, "lang": "en", "fields": fields}})


def service(tenant, **conf):
    secrets = {f"PP_SECRET_{k.upper()}": v for k, v in SECRETS.items()}
    return app.Service(dict(secrets, **conf), tenant, now=NOW)


def call(svc, route: str, raw: bytes, secret: str | None = None):
    sub = app.ROUTES[route]
    return svc.handle("POST", route, signed(raw, secret or SECRETS[sub]), raw)
