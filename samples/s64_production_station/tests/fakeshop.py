"""A stand-in for the retailer's iVendNext, for S64's service tests: the record API (filters, grouped reads, ``modified``
checks, a unique field), the till's partner calls the service makes (get_count, bulk_update, run_report's POS Sale
Report) and the engine's label encoder and barcode reader, with a price-in-barcode mask like a thrift shop's: two start
digits, the item's 5-digit barcode, the price in cents in 5 digits and one filler digit. Stock entries submitted as
they are made move the shop's stock, so a test can count what a cart posted.

``old_engine = True`` makes the encoder write a price as the engine did before its label fix of 12 October 2026 (the
product of a binary float, its last five characters kept): $19.99 then reads back as $999.98.
"""

from __future__ import annotations

import datetime
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "service"))
import app  # noqa: E402

SITE = "thrift.example.com"
SECRET, WORK_SECRET = "link-secret-for-tests", "work-secret-for-tests"
PAGE = "https://production-station.example.app"
ROOM, STORE, OUTLET = "Processing room - GW", "Store 12 - GW", "Outlet - GW"
COMPANY = "Thrift Test Co"
SENTINEL = "29"


def stamp(t: float, zone: str) -> str:
    import zoneinfo
    return datetime.datetime.fromtimestamp(t, zoneinfo.ZoneInfo(zone)).replace(tzinfo=None).isoformat(sep=" ")


class Shop:
    def __init__(self, clock, zone="UTC"):
        self.clock, self.zone = clock, zone
        self.db: dict = {}
        self.seq: dict = {}
        self.calls: list = []
        self.stock: dict = {}            # (item, warehouse) -> qty
        self.values: dict = {}           # (item, warehouse) -> stock value
        self.sales: list = []            # (day, warehouse, item, qty) the till sold
        self.old_engine = False
        self.fail: dict = {}             # op -> (after how many more calls, "refuse" | "lose" | "slow")
        self.no_grouping = False         # the record API refuses a grouped read
        self.settings_rights = True
        self.seed()

    # ── the shop's records ──
    def put(self, doctype, name, **values):
        rec = dict(values, name=name, doctype=doctype, modified=stamp(self.clock(), self.zone),
                   creation=values.get("creation") or stamp(self.clock(), self.zone))
        rec.setdefault("_order", self.clock() + len(self.db.get(doctype, {})) * 1e-6)
        self.db.setdefault(doctype, {})[name] = rec
        return rec

    def seed(self):
        self.put("System Settings", "System Settings", time_zone=self.zone)
        self.put("Barcode Mask", "Thrift label", start_sentinel=SENTINEL)
        for code, group, colour, bar in (("TOPS-BLU", "Women's tops", "Blue", "70102"),
                                         ("TOPS-GRN", "Women's tops", "Green", "70103"),
                                         ("SHIRT-BLU", "Men's shirts", "Blue", "70302"),
                                         ("SHIRT-GRN", "Men's shirts", "Green", "70303")):
            self.put("Item", code, item_group=group, pp_pst_tag_colour=colour, custom_barcode_mask="Thrift label",
                     disabled=0, stock_uom="Nos", barcodes=[{"barcode": bar}])
        for wh, store in ((ROOM, 0), (STORE, 1), (OUTLET, 1)):
            self.put("Warehouse", wh, custom_is_retail_store=store)
        self.put("PP PST Settings", COMPANY, company=COMPANY, room=ROOM, currency="USD", tag_width_mm=50, tag_height_mm=30,
                 first_week="2026-11-02", day_colour="", day_colour_on=None,
                 colours=[{"colour": "Blue", "idx": 1}, {"colour": "Green", "idx": 2}],
                 workers=[{"worker_name": "Ana", "active": 1, "idx": 1}, {"worker_name": "Ben", "active": 1, "idx": 2},
                          {"worker_name": "Cy", "active": 0, "idx": 3}],
                 price_points=[{"category": "Women's tops", "price": 4.99, "idx": 1},
                               {"category": "Women's tops", "price": 6.99, "idx": 2},
                               {"category": "Women's tops", "price": 19.99, "idx": 3},
                               {"category": "Men's shirts", "price": 6.99, "idx": 4}],
                 places=[{"warehouse": STORE, "label": "Store 12", "idx": 1}, {"warehouse": OUTLET, "label": "Outlet", "idx": 2},
                         {"warehouse": ROOM, "label": "Keep here", "idx": 3}])
        self.put("PP PST Station", "PST-S-00001", title="Station 3", settings=COMPANY, number=0, link="", made_for="")

    def next_name(self, doctype):
        prefix = {"PP PST Tag": "PST-T-", "PP PST Cart": "PST-C-", "PP PST Report": "PST-R-", "Stock Entry": "MAT-STE-",
                  "PP PST Station": "PST-S-"}.get(doctype, doctype[:3].upper() + "-")
        self.seq[doctype] = self.seq.get(doctype, 0) + 1
        return f"{prefix}{self.seq[doctype]:05d}"

    def _fault(self, op):
        f = self.fail.get(op)
        if not f:
            return None
        n, kind = f
        if n > 0:
            self.fail[op] = (n - 1, kind)
            return None
        del self.fail[op]
        return kind

    def _before(self, op):
        if self._fault(op) == "refuse":
            raise app.TenantError(f"{op} -> HTTP 417", 417, "ValidationError")

    def _after(self, op):
        if self._fault(op + ":lose") == "lose":
            raise app.TenantError(f"{op} -> TimeoutError")   # written, and the answer lost

    # ── the door the service uses (app.Tenant's methods) ──
    def doc(self, doctype, name):
        self.calls.append(("doc", doctype, name))
        self._before("doc:" + doctype)
        if doctype == "System Settings" and not self.settings_rights:
            raise app.TenantError("GET System Settings -> HTTP 403", 403, "PermissionError")
        rec = self.db.get(doctype, {}).get(name)
        if rec is None:
            raise app.TenantError(f"GET {doctype} -> HTTP 404", 404, "DoesNotExistError")
        return json.loads(json.dumps({k: v for k, v in rec.items() if k != "_order"}))

    @staticmethod
    def _match(rec, filters):
        for fld, op, val in filters:
            have = rec.get(fld)
            if op == "=" and not (have == val or (str(have) == str(val) and have is not None)):
                if not (isinstance(have, str) and isinstance(val, str) and have.lower() == val.lower()):
                    return False
            elif op == "!=" and have == val:
                return False
            elif op == "in" and have not in val:
                return False
            elif op == "is" and val == "set" and not have:
                return False
            elif op == "is" and val == "not set" and have:
                return False
            elif op == ">=" and not (have is not None and str(have) >= str(val)):
                return False
            elif op == "<=" and not (have is not None and str(have) <= str(val)):
                return False
        return True

    def rows(self, doctype, fields, filters, limit=500, start=0, order_by="", group_by=""):
        self.calls.append(("rows", doctype, json.loads(json.dumps(filters)), group_by))
        self._before("rows:" + doctype)
        if limit == 20 and doctype != "PP PST Cart":
            raise AssertionError("a read with the record API's default page of 20")
        recs = [r for r in self.db.get(doctype, {}).values() if self._match(r, filters)]
        key, rev = (order_by.split() + ["asc"])[:2] if order_by else ("_order", "asc")
        key = "_order" if key in ("creation", "_order") else key
        recs.sort(key=lambda r: (r.get(key) is None, r.get(key)), reverse=rev == "desc")
        if group_by:
            if self.no_grouping:
                raise app.TenantError(f"GET {doctype} -> HTTP 417", 417, "DataError")
            keys = [k.strip() for k in group_by.split(",")]
            acc: dict = {}
            for r in recs:
                k = tuple(r.get(x) for x in keys)
                acc[k] = acc.get(k, 0) + int(r.get("quantity") or 0)
            out = [dict(zip(keys, k), pieces=v) for k, v in acc.items()]
            return out[start:start + limit]
        out = []
        for r in recs:
            if doctype == "Item" and any(f.startswith("barcodes.") for f in fields):
                for b in r.get("barcodes") or [{}]:
                    out.append({**{f: r.get(f) for f in fields if "." not in f}, "barcode": b.get("barcode")})
            else:
                out.append({f: r.get(f) for f in fields})
        return out[start:start + limit]

    def insert(self, doctype, body, timeout=None):
        self.calls.append(("insert", doctype, body.get("purpose") or ""))
        self._before("insert:" + doctype)
        if doctype == "PP PST Cart" and body.get("open_for") and any(
                r.get("open_for") == body["open_for"] for r in self.db.get(doctype, {}).values()):
            raise app.TenantError("POST PP PST Cart -> HTTP 409", 409, "DuplicateEntryError")
        name = self.next_name(doctype)
        rec = self.put(doctype, name, **body)
        if doctype == "Stock Entry" and body.get("docstatus") == 1:
            for line in body["items"]:
                q = line["qty"]
                if line.get("s_warehouse"):
                    k = (line["item_code"], line["s_warehouse"])
                    if self.stock.get(k, 0) < q:
                        self.db[doctype].pop(name)
                        raise app.TenantError("POST Stock Entry -> HTTP 417", 417, "NegativeStockError")
                    self.stock[k] -= q
                if line.get("t_warehouse"):
                    k = (line["item_code"], line["t_warehouse"])
                    self.stock[k] = self.stock.get(k, 0) + q
                    self.values[k] = self.values.get(k, 0) + q * float(line.get("basic_rate") or 0)
        self._after("insert:" + doctype)
        return self.doc(doctype, name)

    def update(self, doctype, name, body):
        self.calls.append(("update", doctype, name, sorted(body)))
        self._before("update:" + doctype)
        rec = self.db.get(doctype, {}).get(name)
        if rec is None:
            raise app.TenantError(f"PUT {doctype} -> HTTP 404", 404, "DoesNotExistError")
        if "modified" in body and body["modified"] != rec["modified"]:
            raise app.TenantError(f"PUT {doctype} -> HTTP 417", 417, app.STALE)
        if doctype == "PP PST Cart" and body.get("open_for") and any(
                r.get("open_for") == body["open_for"] and r["name"] != name for r in self.db[doctype].values()):
            raise app.TenantError("PUT PP PST Cart -> HTTP 409", 409, "DuplicateEntryError")
        rec.update({k: v for k, v in body.items() if k != "modified"})
        self.clock.t += 0.001                      # a save always writes a new modified
        rec["modified"] = stamp(self.clock(), self.zone)
        self._after("update:" + doctype)
        return self.doc(doctype, name)

    def call(self, verb, body=None, query=None, timeout=None):
        self.calls.append(("call", verb))
        self._before("call:" + verb)
        if verb == "get_count":
            return len(self.rows(query["doctype"], ["name"], json.loads(query["filters"]), limit=100000))
        if verb == "bulk_update":
            for d in json.loads(body["docs"]):
                rec = self.db[d["doctype"]][d["docname"]]
                rec.update({k: v for k, v in d.items() if k not in ("doctype", "docname")})
            self._after("call:bulk_update")
            return {"failed_docs": []}
        raise AssertionError("unexpected call " + verb)

    def engine(self, path, query):
        self.calls.append(("engine", path.rsplit(".", 1)[-1]))
        self._before("engine")
        if path == app.LABEL:
            item = self.db["Item"].get(query["item_code"])
            if not item or not item.get("custom_barcode_mask") or not item.get("barcodes"):
                return ""
            price = float(query["price"])
            cents = (str(price * 100)[-5:] if self.old_engine else str(int(round(price * 100)))).zfill(5)[-5:]
            return SENTINEL + item["barcodes"][0]["barcode"] + cents + "0"
        if path == app.RESOLVE:
            code = query["barcode"]
            if not code.startswith(SENTINEL) or len(code) != 13:
                return {"barcode_masked": False}
            try:
                price = float(code[7:12]) / 100
            except ValueError:
                return {"barcode_masked": True, "error": "Barcode mask resolution failed. Check Error Log."}
            return {"barcode_masked": True, "item_barcode": code[2:7], "item_code": None, "scanned_price": price}
        raise AssertionError(path)

    def report(self, name, filters, timeout=None):
        self.calls.append(("report", name, filters.get("warehouse"), filters.get("from_date"), filters.get("to_date")))
        if self._fault("report") == "refuse":
            raise app.ReportRefused(f"POST {name} -> HTTP 403", 403)
        assert name == app.POS_SALE_REPORT and filters["report_type"] == "Item"
        by: dict = {}
        for day, wh, item, qty in self.sales:
            if wh == filters["warehouse"] and filters["from_date"] <= day <= filters["to_date"]:
                by[item] = by.get(item, 0) + qty
        return {"message": {"columns": [{"fieldname": "item"}, {"fieldname": "unit_solds"}],
                            "result": [[i, q] for i, q in sorted(by.items())]}}

    # ── what a test reads back ──
    def tags(self, **match):
        return [r for r in self.db.get("PP PST Tag", {}).values() if all(r.get(k) == v for k, v in match.items())]

    def entries(self, purpose=None):
        return [r for r in self.db.get("Stock Entry", {}).values() if purpose is None or r.get("purpose") == purpose]
