"""An in-memory shop for S30's tests: the source unit table, Serial Nos, batches, lots of stock and the documents the
migration makes. It answers the same methods as ``shop.Shop`` that the scripts call; nothing here is iVendNext's code.
A receipt makes its serial numbers with their batch and store; a count to 0 empties the old lot."""

from __future__ import annotations


class FakeShop:
    def __init__(self, units=(), stock=None, serials=None, batches=None, rates=None):
        self.units = [dict(u) for u in units]           # the source table's rows
        self.stock = dict(stock or {})                  # (item, store, batch) -> quantity
        self.rates = dict(rates or {})                  # (item, store, batch) -> valuation rate
        self.sn = {k: dict(v) for k, v in (serials or {}).items()}   # code -> Serial No
        self.batch = dict(batches or {})                # batch -> {"item", "expiry_date"}
        self.docs = []                                  # (record type, doc) of every insert
        self.drafts = 0

    # what migrate.py and units_report.py call
    def list(self, dt, filters, fields, parent=None, order_by=None):
        assert dt == "PP UNC Unit", dt
        return [{k: u.get(k) for k in fields} for u in self.units]

    def list_in(self, dt, field, values, fields, other=(), parent=None):
        assert dt == "Batch"
        return [{"name": b} for b in values if b in self.batch]

    def get(self, dt, name):
        assert dt == "Batch"
        return dict(self.batch[name], name=name) if name in self.batch else None

    def serials(self, codes):
        up = {c.upper() for c in codes}
        return {k: v for k, v in self.sn.items() if k.upper() in up}

    def stock_adjustment_account(self, company):
        return "Stock Adjustment - DR"

    def lot_stock(self, company, lots):
        self.drafts += 1
        return {lot: (self.stock.get(lot, 0), self.rates.get(lot, 0)) for lot in lots if self.stock.get(lot, 0)}

    def insert(self, dt, doc):
        self.docs.append((dt, doc))
        if dt == "Batch":
            assert doc["batch_id"] not in self.batch, f"batch {doc['batch_id']} made twice"
            self.batch[doc["batch_id"]] = {"item": doc["item"], "expiry_date": doc.get("expiry_date")}
        elif dt == "Stock Entry":
            for r in doc["items"]:
                codes = r["serial_no"].split("\n")
                assert len(codes) == r["qty"]
                for c in codes:
                    assert c not in self.sn, f"serial {c} made twice"
                    self.sn[c] = {"name": c, "item_code": r["item_code"], "batch_no": r["batch_no"],
                                  "warehouse": r["t_warehouse"], "status": "Active"}
                lot = (r["item_code"], r["t_warehouse"], r["batch_no"])
                self.stock[lot] = self.stock.get(lot, 0) + r["qty"]
        elif dt == "Stock Reconciliation":
            for r in doc["items"]:
                self.stock[(r["item_code"], r["warehouse"], r["batch_no"])] = r["qty"]
        return dict(doc, name=f"{dt[:3].upper()}-{len(self.docs):04d}")

    def inserted(self, dt):
        return [d for t, d in self.docs if t == dt]
