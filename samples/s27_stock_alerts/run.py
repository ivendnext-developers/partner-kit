#!/usr/bin/env python3
"""S27 — stock alerts and a draft transfer request, on a schedule. Python 3.9+, standard library only.

    STK_KEY=… STK_SECRET=… python3 run.py --base https://shop.example

One run, in order:

  READ     — the settings record ``Default``, the warehouses, the items' reorder rows, the stock of the watched stores,
             the batches that expire within the settings' days, and each batch's quantity per store (from the batch
             records of submitted stock movements). Records only: no report is run.
  ALERTS   — every low stock and every near expiry found, keyed by kind, store, item, batch and day. A key already
             written today is skipped, so a second run the same day writes nothing new.
  REQUEST  — the new alerts' lines go on ONE draft transfer request per store and day, titled ``PP-STK <store> <day>``
             (the stamp). A run that finds today's draft adds its lines to it; a line already on an open request of the
             service for that store (a draft, or submitted and not yet transferred) is not added twice. A request
             without the stamp is a person's: never read, never changed. Nothing is ever submitted, and a submitted
             request is never changed: a person edits the draft and submits it.
  WRITE    — the alert records, each naming the draft it joined. The shop's notification on a new alert tells people.

The lines are written before the alerts: a run that stops between the two finds its lines on the draft next time and
only writes the alerts.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import alerts as A  # noqa: E402
import feed_client as F  # noqa: E402

ALERT, SETTINGS, MR = "PP STK Alert", "PP STK Settings", "Material Request"
DONE = ["Stopped", "Cancelled", "Transferred", "Issued", "Received"]


class Shop:
    """The shop over the record API. Nothing here decides anything."""

    def __init__(self, api: F.Api):
        self.api = api

    @staticmethod
    def _q(dt, name=None):
        p = "/api/resource/" + urllib.parse.quote(dt)
        return p if name is None else f"{p}/{urllib.parse.quote(name, safe='')}"

    def _list(self, dt, filters, fields, order_by: str | None = "name asc"):
        """Every row (no page limit). A read joined to child rows sends no order: there a bare name is ambiguous."""
        p = {"filters": json.dumps(filters), "fields": json.dumps(fields), "limit_page_length": 0}
        if order_by:
            p["order_by"] = order_by
        return self.api.call("GET", self._q(dt), p).get("data", [])

    def _get(self, dt, name):
        try:
            return self.api.call("GET", self._q(dt, name)).get("data")
        except F.FeedError as e:
            if str(e).startswith("404"):
                return None
            raise

    def settings(self) -> dict | None:
        return self._get(SETTINGS, "Default")

    def warehouses(self) -> list[dict]:
        return self._list("Warehouse", [], ["name", "is_group", "disabled", "company"])

    def reorder_rows(self) -> list[dict]:
        """Every reorder row with a level, one per row (the item's child rows, read through the item)."""
        rows = self._list("Item", [["disabled", "=", 0], ["Item Reorder", "warehouse_reorder_level", ">", 0]],
                          ["name", "reorder_levels.warehouse", "reorder_levels.warehouse_reorder_level",
                           "reorder_levels.warehouse_reorder_qty", "reorder_levels.material_request_type"], order_by=None)
        return [{**r, "item": r["name"]} for r in rows]

    def bins(self, stores: list[str]) -> dict[tuple[str, str], dict]:
        rows = self._list("Bin", [["warehouse", "in", stores]], ["item_code", "warehouse", "projected_qty", "actual_qty", "stock_uom"])
        return {(r["item_code"], r["warehouse"]): r for r in rows}

    def batches(self, last: _dt.date) -> list[dict]:
        return self._list("Batch", [["disabled", "=", 0], ["expiry_date", "<=", last.isoformat()], ["batch_qty", ">", 0]],
                          ["name", "item", "batch_qty", "expiry_date", "stock_uom", "disabled"])

    def batch_stock(self, names: list[str]) -> dict[tuple[str, str], float] | None:
        """Each batch's quantity per warehouse: the sum of its rows (outward rows are below 0) in submitted, uncancelled
        batch records, a till's sale not yet merged left out (its stock has not moved). Read 100 batches at a time.
        None when the key may not read them (the alert then says the batch's total)."""
        out: dict[tuple[str, str], float] = {}
        for i in range(0, len(names), 100):
            part = names[i:i + 100]
            try:
                rows = self._list("Serial and Batch Bundle",
                                  [["docstatus", "=", 1], ["is_cancelled", "=", 0], ["voucher_type", "!=", "POS Invoice"],
                                   ["Serial and Batch Entry", "batch_no", "in", part]],
                                  ["warehouse", "entries.batch_no", "entries.qty"], order_by=None)
            except F.FeedError as e:
                if str(e).startswith("403"):
                    return None
                raise
            for r in rows:
                if r.get("batch_no") in part:
                    k = (r["batch_no"], r["warehouse"])
                    out[k] = out.get(k, 0.0) + float(r.get("qty") or 0)
        return out

    def open_requests(self) -> list[dict]:
        """Every transfer request still open — a draft, or submitted and not yet transferred — the service's and people's
        alike: the service tells them apart by title."""
        return self._list(MR, [["docstatus", "<", 2], ["material_request_type", "=", "Material Transfer"],
                               ["status", "not in", DONE]], ["name", "title", "docstatus"])

    def request(self, name: str) -> dict:
        return self._get(MR, name)

    def insert_request(self, doc: dict) -> dict:
        return self.api.call("POST", self._q(MR), body={"doctype": MR, **doc})["data"]

    def update_request(self, name: str, items: list[dict]) -> dict:
        return self.api.call("PUT", self._q(MR, name), body={"items": items})["data"]

    def alert(self, key: str) -> dict | None:
        return self._get(ALERT, key)

    def insert_alert(self, doc: dict) -> bool:
        """False when the shop already holds that key (two runs at once): the record's name is the key."""
        try:
            self.api.call("POST", self._q(ALERT), body={"doctype": ALERT, **doc})
            return True
        except F.FeedError as e:
            if str(e).startswith("409"):
                return False
            raise


def report() -> dict:
    return {"alerts": 0, "requests_made": [], "lines_added": 0, "already_on_a_draft": 0, "alert_only": 0, "known": True}


class Service:
    def __init__(self, shop):
        self.shop = shop

    def run(self, today: _dt.date | None = None) -> dict:
        today = today or _dt.date.today()
        rep = report()
        st = self.shop.settings()
        if not st or not st.get("enabled"):
            return {**rep, "skipped": "the settings record Default is missing or switched off"}
        whs = self.shop.warehouses()
        watched = A.stores(st, whs)
        company = next((w.get("company") for w in whs if w["name"] == st.get("source_warehouse")), None)
        days = int(st.get("expiry_days") or 0)
        batches = self.shop.batches(A.last_day(today, days))
        per_store = self.shop.batch_stock([b["name"] for b in batches])
        rep["known"] = per_store is not None
        found = (A.low_stock(self.shop.reorder_rows(), self.shop.bins(watched), watched)
                 + A.near_expiry(batches, per_store, watched, today, days))

        new = []
        for a in found:                                  # one alert per key and day: a second run writes nothing
            a["key"] = A.key(a["kind"], a.get("store"), a["item"], a.get("batch"), today)
            if self.shop.alert(a["key"]) is None:
                new.append(a)

        per = A.lines(new, st, today)
        listed = self.shop.open_requests()
        for store, want in per.items():
            mine = [self.shop.request(r["name"]) for r in listed if A.ours_for(r.get("title"), store)]   # a person's is never read
            need = []
            for line in want:
                on = next((d for d in mine for it in d.get("items") or [] if A.same_line(line, it)), None)
                if on:
                    line["request"] = on["name"]
                    rep["already_on_a_draft"] += 1
                else:
                    need.append(line)
            if not need:
                continue
            title = A.stamp(store, today)
            doc = next((d for d in mine if d["title"] == title and d.get("docstatus") == 0), None)   # a submitted one: never
            rows, left = A.place(need, doc["items"] if doc else [])
            placed = [ln for ln in need if not any(ln is x for x in left)]
            if not placed:
                continue
            if doc:
                doc = self.shop.update_request(doc["name"], rows)
            else:
                doc = self.shop.insert_request({"material_request_type": "Material Transfer", "title": title, "company": company,
                                                "transaction_date": today.isoformat(), "schedule_date": today.isoformat(),
                                                "docstatus": 0, "items": rows})
                rep["requests_made"].append(doc["name"])
            rep["lines_added"] += len(placed)
            for line in placed:
                line["request"] = doc["name"]

        for a in new:
            req = (a.get("line") or {}).get("request")
            rep["alert_only"] += not req
            doc = {"alert_key": a["key"], "kind": a["kind"], "store": a.get("store"), "item": a["item"],
                   "batch": a.get("batch"), "qty": a["qty"], "level": a.get("level"), "expiry_date": a.get("expiry_date"),
                   "alert_day": today.isoformat(), "request": req, "notify_user": st.get("notify_user"),
                   "store_qty_known": int(a["kind"] == A.LOW or bool(a.get("known")))}
            rep["alerts"] += self.shop.insert_alert({k: v for k, v in doc.items() if v is not None})
        return rep


def main(argv=None):
    p = argparse.ArgumentParser(description="S27 — stock alerts and a draft transfer request")
    p.add_argument("--base", required=True)
    p.add_argument("--today", help="test only: the day of the run (YYYY-MM-DD)")
    a = p.parse_args(argv)
    key, secret = os.environ.get("STK_KEY"), os.environ.get("STK_SECRET")
    if not key or not secret:
        sys.exit("set STK_KEY and STK_SECRET in the environment")
    today = _dt.date.fromisoformat(a.today) if a.today else None
    print(json.dumps(Service(Shop(F.Api(a.base, key, secret))).run(today)), flush=True)


if __name__ == "__main__":
    try:
        main()
    except (F.FeedError, RuntimeError) as e:
        sys.exit(f"STK_ERROR {e}")
