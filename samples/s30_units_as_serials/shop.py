"""S30's calls to the shop: the record API only (``/api/resource/…``), with the key of the user who runs the script.
Nothing here decides anything; ``units.py`` does. Standard library only.

The shop's records it reads: Serial No, Serial and Batch Bundle and its rows (Serial and Batch Entry, read with the
bundle as parent), Stock Reconciliation, and the source unit table. It writes: Batch, Stock Entry (a receipt), Stock
Reconciliation (the old item counted to 0), and, in ``apply_config.py``, Stock Settings, Warehouse, Item, Item Price.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import feed_client as F  # noqa: E402

CHUNK = 100          # names per "in" filter, so an address stays short
MARK = "PP USN migration"   # written in the remarks of every document the migration makes, so a person can find them


def q(dt: str, name: str | None = None) -> str:
    p = "/api/resource/" + urllib.parse.quote(dt)
    return p if name is None else f"{p}/{urllib.parse.quote(name, safe='')}"


class Shop:
    def __init__(self, api):
        self.api = api

    @classmethod
    def from_env(cls):
        return cls(F.Api(os.environ["PP_BASE"], os.environ["PP_KEY"], os.environ["PP_SECRET"], timeout=60))

    # ── reading ──────────────────────────────────────────────────────────────────────────────────────────────────
    def list(self, dt, filters, fields, parent=None, order_by="name asc"):
        p = {"filters": json.dumps(filters), "fields": json.dumps(fields), "order_by": order_by, "limit_page_length": 0}
        if parent:
            p["parent"] = parent
        return self.api.call("GET", q(dt), p).get("data", [])

    def list_in(self, dt, field, values, fields, other=(), parent=None):
        out, values = [], sorted(set(values))
        for i in range(0, len(values), CHUNK):
            out += self.list(dt, [[field, "in", values[i:i + CHUNK]], *other], fields, parent=parent)
        return out

    def get(self, dt, name):
        try:
            return self.api.call("GET", q(dt, name)).get("data")
        except F.FeedError as e:
            if str(e).startswith("404"):
                return None
            raise

    # ── writing ──────────────────────────────────────────────────────────────────────────────────────────────────
    def insert(self, dt, doc):
        return self.api.call("POST", q(dt), body=dict(doc, doctype=dt)).get("data")

    def update(self, dt, name, fields):
        return self.api.call("PUT", q(dt, name), body=fields).get("data")

    def delete(self, dt, name):
        return self.api.call("DELETE", q(dt, name))

    # ── what the scripts need ────────────────────────────────────────────────────────────────────────────────────
    def serials(self, codes):
        """{code: Serial No} for the codes that are serial numbers already (any item)."""
        rows = self.list_in("Serial No", "name", codes, ["name", "item_code", "batch_no", "warehouse", "status"])
        return {r["name"]: r for r in rows}

    def serials_of(self, items):
        return self.list_in("Serial No", "item_code", items, ["name", "item_code", "batch_no", "warehouse", "status"])

    def movements(self, serials):
        """{serial: [movement, …]}: each unit's submitted, uncancelled stock movements, read from the bundles' rows."""
        rows = self.list_in("Serial and Batch Entry", "serial_no", serials, ["parent", "serial_no"],
                            parent="Serial and Batch Bundle")
        bundles = {b["name"]: b for b in self.list_in(
            "Serial and Batch Bundle", "name", [r["parent"] for r in rows],
            ["name", "voucher_type", "voucher_no", "type_of_transaction", "posting_date", "posting_time", "creation"],
            other=[["docstatus", "=", 1], ["is_cancelled", "=", 0]])}
        out: dict[str, list] = {}
        for r in rows:
            if r["parent"] in bundles:
                out.setdefault(r["serial_no"], []).append(bundles[r["parent"]])
        return out

    def lot_stock(self, company, lots):
        """{(item, store, batch): (quantity, valuation rate)} as the shop's own count works it out: a draft Stock
        Reconciliation with a 0 row per lot is saved, its current figures read, and the draft deleted. Nothing is
        booked. A shop with none of these lots in stock refuses the draft (no row would change): then every lot is 0."""
        rows = [{"item_code": i, "warehouse": w, "batch_no": b, "qty": 0, "use_serial_batch_fields": 1} for i, w, b in lots]
        if not rows:
            return {}
        doc = {"company": company, "purpose": "Stock Reconciliation", "remarks": f"{MARK}: a draft to read the old stock (deleted)",
               "items": rows}
        try:
            draft = self.insert("Stock Reconciliation", doc)
        except F.FeedError as e:
            if "None of the items have any change" in str(e):
                return {}
            raise
        figures = {(r["item_code"], r["warehouse"], r["batch_no"]): (float(r.get("current_qty") or 0),
                                                                     float(r.get("current_valuation_rate") or 0))
                   for r in draft["items"]}
        try:
            self.delete("Stock Reconciliation", draft["name"])
        except F.FeedError as e:
            raise SystemExit(f"the draft count {draft['name']} was read but could not be deleted ({e}): delete it in Desk, "
                             "then run again") from None
        return figures

    def stock_adjustment_account(self, company):
        return (self.get("Company", company) or {}).get("stock_adjustment_account")
