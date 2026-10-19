#!/usr/bin/env python3
"""S7 — keep a customer's own system in step with iVendNext. Python 3.9+, standard library only.

    SYNC_KEY=… SYNC_SECRET=… python3 sync.py run --base https://shop.example --app "PP SYNC" --erp state/erp.sqlite \
        --state state/sync.sqlite --warehouse "Store - X" --company "My Company" --watch 30

Two directions, both safe to stop at any moment:

  OUT  — what the ERP changed goes to the shop: items (created, renamed, disabled — never deleted), prices (one Item Price
         per price list) and stock (a Stock Entry the shop's engine books — the sync never sets a quantity). The ERP
         numbers each change; the sync's CURSOR is the last number done. Every write to the shop is keyed so a second
         delivery finds its own earlier work (an item by its code, a price by item + list, a stock entry by the key in its
         remarks) — a crash between the write and the cursor does no harm.
  IN   — what the shop booked comes to the ERP, once each: sales and returns, read from the event feed
         (``tools/feed_client``, recipes/event_feed.md). The seen-set and the ERP write sit under the feed client's rules;
         the ERP write is keyed on the shop's invoice number, so a replay writes nothing.

  RECONCILE — a nightly, read-only pass: per day the counts and totals of booked sales and returns on both sides, every
         record on one side only, every total that differs, every return not linked to its sale, stock on hand on both
         sides, items and prices. It REPORTS by name. It never changes the shop or the ERP: a difference in money is a
         person's decision.

The identity map (``id_map`` in the state file) pairs ERP item id ↔ the shop's item code and ERP document id ↔ the shop's
invoice number. Today's feed key is not scoped to one application (recipes/event_feed.md §3): this sample uses the
engine transport and says so.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "tools", "feed_client"))
import feed_client as F  # noqa: E402
from erp import Erp  # noqa: E402

PREFIX = "PP-SYN-"     # the shop's item code is the ERP's id behind this prefix; the map is the authority, the prefix a convention


class Shop:
    """The shop, over the record API. Every method is one or two calls; nothing here computes money."""

    def __init__(self, api: F.Api, warehouse: str, company: str):
        self.api, self.warehouse, self.company = api, warehouse, company

    @staticmethod
    def _q(dt):
        return "/api/resource/" + urllib.parse.quote(dt)

    def _get(self, dt, name):
        try:
            return self.api.call("GET", f"{self._q(dt)}/{urllib.parse.quote(name)}").get("data")
        except F.FeedError as e:
            if str(e).startswith("404"):
                return None
            raise

    def _list(self, dt, filters, fields, **kw):
        return self.api.call("GET", self._q(dt), {"filters": json.dumps(filters), "fields": json.dumps(fields),
                                                  "limit_page_length": 0, **kw}).get("data", [])

    def item(self, code):
        return self._get("Item", code)

    def create_item(self, code, name, group):
        self.api.call("POST", self._q("Item"), body={"doctype": "Item", "item_code": code, "item_name": name, "item_group": group,
                                                     "stock_uom": "Nos", "is_stock_item": 1})

    def update_item(self, code, **fields):
        self.api.call("PUT", f"{self._q('Item')}/{urllib.parse.quote(code)}", body=fields)

    def item_price(self, code, price_list):
        rows = self._list("Item Price", [["item_code", "=", code], ["price_list", "=", price_list], ["selling", "=", 1]],
                          ["name", "price_list_rate"])
        return rows[0] if rows else None

    def create_item_price(self, code, price_list, rate):
        self.api.call("POST", self._q("Item Price"), body={"doctype": "Item Price", "item_code": code, "price_list": price_list,
                                                           "price_list_rate": rate, "selling": 1})

    def update_item_price(self, name, rate):
        self.api.call("PUT", f"{self._q('Item Price')}/{urllib.parse.quote(name)}", body={"price_list_rate": rate})

    def stock_entry_for(self, key):
        rows = self._list("Stock Entry", [["remarks", "=", key], ["docstatus", "=", 1]], ["name"])
        return rows[0]["name"] if rows else None

    def book_stock(self, key, code, qty, rate):
        """A Stock Entry the engine books: a Material Receipt for goods in, a Material Issue for goods out."""
        kind = "Material Receipt" if qty > 0 else "Material Issue"
        row = {"item_code": code, "qty": abs(qty), "basic_rate": rate}
        row["t_warehouse" if qty > 0 else "s_warehouse"] = self.warehouse
        res = self.api.call("POST", self._q("Stock Entry"), body={
            "doctype": "Stock Entry", "stock_entry_type": kind, "purpose": kind, "company": self.company, "docstatus": 1,
            "remarks": key, "items": [row]})
        return res["data"]["name"]

    def bin_qty(self, code):
        rows = self._list("Bin", [["item_code", "=", code], ["warehouse", "=", self.warehouse]], ["actual_qty"])
        return float(rows[0]["actual_qty"]) if rows else 0.0

    def invoice(self, name):
        d = self._get("POS Invoice", name)
        if d is None:
            return None
        return {"name": d["name"], "is_return": int(d.get("is_return") or 0), "return_against": d.get("return_against"),
                "posting_date": d["posting_date"], "customer": d.get("customer"), "grand_total": float(d["grand_total"]),
                "docstatus": d["docstatus"], "creation": d["creation"],
                "items": [{"item_code": i["item_code"], "qty": float(i["qty"]), "amount": float(i["amount"])} for i in d.get("items", [])]}

    def invoices_since(self, since):
        return [dict(r, grand_total=float(r["grand_total"]), is_return=int(r["is_return"] or 0)) for r in self._list(
            "POS Invoice", [["docstatus", "=", 1], ["creation", ">=", since]],
            ["name", "is_return", "return_against", "posting_date", "grand_total", "creation"])]


def init_state(db):
    db.execute("create table if not exists cursor (k text primary key, seq integer not null)")
    db.execute("create table if not exists id_map (kind text, erp_id text, shop_name text, primary key (kind, erp_id))")


def cursor_of(db) -> int:
    r = db.execute("select seq from cursor where k='erp_changes'").fetchone()
    return r[0] if r else 0


def push_out(erp: Erp, db, shop: Shop, crash_after: int | None = None) -> dict:
    """Everything the ERP changed since the cursor, oldest first, stopping at the first failure (order matters: an item
    before its price and its stock). The cursor moves after each change is fully written."""
    n = {"changes": 0, "items": 0, "prices": 0, "stock_entries": 0, "already_there": 0, "skipped_deleted": 0}
    for ch in erp.changes_after(cursor_of(db)):
        if ch["kind"] == "item":
            _item(erp, db, shop, ch["ref"], n)
        elif ch["kind"] == "price":
            _price(erp, shop, ch["ref"], n)
        elif ch["kind"] == "movement":
            _movement(erp, shop, int(ch["ref"]), n)
        n["changes"] += 1
        if crash_after is not None and n["changes"] >= crash_after:       # the write is done, the cursor is not
            raise SystemExit(f"CRASH (injected) after writing change {ch['seq']} to the shop, before saving the cursor")
        db.execute("insert into cursor values ('erp_changes', ?) on conflict(k) do update set seq=excluded.seq", (ch["seq"],))
    return n


def _item(erp, db, shop, erp_id, n):
    it, code = erp.item(erp_id), PREFIX + erp_id
    cur = shop.item(code)
    if it["deleted"]:                                   # a deleted ERP item is DISABLED in the shop, never deleted
        if cur and not cur["disabled"]:
            shop.update_item(code, disabled=1)
            n["items"] += 1
        return
    if cur is None:
        shop.create_item(code, it["name"], it["item_group"])
        n["items"] += 1
    elif cur["item_name"] != it["name"] or cur["item_group"] != it["item_group"] or cur["disabled"]:
        shop.update_item(code, item_name=it["name"], item_group=it["item_group"], disabled=0)
        n["items"] += 1
    else:
        n["already_there"] += 1
    db.execute("insert or ignore into id_map values ('item', ?, ?)", (erp_id, code))


def _price(erp, shop, ref, n):
    erp_id, plist = ref.split("|", 1)
    code = PREFIX + erp_id
    if erp.item(erp_id)["deleted"]:           # the ERP deleted the item since: its shop item is disabled (or never made); nothing more to write
        n["skipped_deleted"] += 1
        return
    price = dict((r["price_list"], r["price"]) for r in erp.prices_of(erp_id))[plist]
    if shop.item(code) is None:
        raise RuntimeError(f"the price of {erp_id} came before its item reached the shop")
    cur = shop.item_price(code, plist)
    if cur is None:
        shop.create_item_price(code, plist, price)
        n["prices"] += 1
    elif abs(float(cur["price_list_rate"]) - price) > 1e-9:
        shop.update_item_price(cur["name"], price)
        n["prices"] += 1
    else:
        n["already_there"] += 1


def _movement(erp, shop, mid, n):
    mv = erp.movement(mid)
    if erp.item(mv["erp_id"])["deleted"]:
        n["skipped_deleted"] += 1
        return
    key = f"PP-SYNC {erp.identity()} mv:{mid}"      # the ERP's own id inside the key: movement 1 of another system is not this one's
    if shop.stock_entry_for(key):                        # an earlier attempt wrote it: the key is how a retry knows
        n["already_there"] += 1
        return
    code = PREFIX + mv["erp_id"]
    if shop.item(code) is None:
        raise RuntimeError(f"stock movement {mid} came before its item reached the shop")
    shop.book_stock(key, code, mv["qty"], mv["unit_cost"] or 1.0)
    n["stock_entries"] += 1


def make_handler(erp: Erp, shop: Shop):
    """The feed handler (``handler(event, store_db)``): sales and returns into the ERP, once each."""
    def handler(ev, db):
        e = ev["event"]
        if e in ("sale.booked", "return.booked"):
            inv = shop.invoice(ev["doc_name"])
            if inv is None:
                raise RuntimeError(f"{ev['doc_name']} cannot be read (deleted, or the key may not read it)")
            lines = []
            for ln in inv["items"]:
                m = db.execute("select erp_id from id_map where kind='item' and shop_name=?", (ln["item_code"],)).fetchone()
                lines.append({"erp_item": m[0] if m else None, **ln})
            return_of = None
            if inv["is_return"]:
                orig = erp.document_by_shop(inv["return_against"] or "")
                return_of = orig["erp_doc_id"] if orig else None
            doc_id, _ = erp.record_document("return" if inv["is_return"] else "order", inv["name"], inv["posting_date"],
                                            inv["grand_total"], inv["customer"], inv["creation"], lines, return_of,
                                            cancelled=1 if inv["docstatus"] == 2 else 0)
            db.execute("insert or ignore into id_map values ('document', ?, ?)", (doc_id, inv["name"]))
        elif e == "sale.cancelled":
            erp.cancel_document(ev["doc_name"])
        # every other event is not this sample's business: it is recorded as seen and marked done
    return handler


def reconcile(erp: Erp, db, shop: Shop, since: str, still_queued: set[str] | None = None) -> dict:
    """The nightly report. Read-only on both sides. ``still_queued``: invoices whose event has not been collected yet
    (late, or failed and waiting) — listed apart, not as differences."""
    still_queued = still_queued or set()
    diffs = []
    s_inv = {h["name"]: h for h in shop.invoices_since(since)}
    e_doc = {d["shop_invoice"]: d for d in erp.documents_since(since)}
    kind = lambda h: "return" if h["is_return"] else "sale"  # noqa: E731
    for name in sorted(set(s_inv) - set(e_doc) - still_queued):
        diffs.append({"what": "booked in the shop, not in the ERP", "name": name, "kind": kind(s_inv[name]),
                      "shop_total": s_inv[name]["grand_total"]})
    for name in sorted(set(e_doc) - set(s_inv)):
        diffs.append({"what": "in the ERP, not booked in the shop (cancelled or removed there)", "name": name,
                      "kind": e_doc[name]["kind"], "erp_total": e_doc[name]["grand_total"]})
    for name in sorted(set(s_inv) & set(e_doc)):
        s, d = s_inv[name], e_doc[name]
        if abs(s["grand_total"] - d["grand_total"]) > 0.005:
            diffs.append({"what": "total differs", "name": name, "shop_total": s["grand_total"], "erp_total": d["grand_total"]})
        if d["kind"] == "return" and not d["return_of"]:
            diffs.append({"what": "return not linked to its sale in the ERP", "name": name, "return_against": s["return_against"]})
    days = {}
    for side, rows in (("shop", [h for n, h in s_inv.items() if n not in still_queued]),
                       ("erp", [dict(d, is_return=d["kind"] == "return") for d in e_doc.values()])):
        for r in rows:
            cell = days.setdefault(r["posting_date"], {}).setdefault(side, {"sales": 0, "sales_total": 0.0, "returns": 0, "returns_total": 0.0})
            k = "returns" if r["is_return"] else "sales"
            cell[k] += 1
            cell[k + "_total"] = round(cell[k + "_total"] + float(r["grand_total"]), 2)
    zero = {"sales": 0, "sales_total": 0.0, "returns": 0, "returns_total": 0.0}
    for day, c in sorted(days.items()):
        if c.get("shop", zero) != c.get("erp", zero):
            diffs.append({"what": "the day's counts or totals differ", "day": day, "shop": c.get("shop", zero), "erp": c.get("erp", zero)})
    mapped = {r[0] for r in db.execute("select erp_id from id_map where kind='item'")}
    for (erp_id,) in erp.db.execute("select erp_id from items where deleted=0 order by erp_id").fetchall():
        if erp_id not in mapped:
            diffs.append({"what": "item in the ERP, never pushed to the shop", "name": PREFIX + erp_id})
    for erp_id, code in db.execute("select erp_id, shop_name from id_map where kind='item'").fetchall():
        it = erp.item(erp_id)
        s_item = shop.item(code)
        if s_item is None:
            diffs.append({"what": "item in the ERP map, absent in the shop", "name": code})
            continue
        if it["deleted"] and not s_item["disabled"]:
            diffs.append({"what": "item deleted in the ERP, still enabled in the shop", "name": code})
        if not it["deleted"]:
            have, want = shop.bin_qty(code), erp.on_hand(erp_id)
            if abs(have - want) > 1e-6:
                diffs.append({"what": "stock on hand differs", "name": code, "shop": have, "erp": want})
            for r in erp.prices_of(erp_id):
                p = shop.item_price(code, r["price_list"])
                if p is None or abs(float(p["price_list_rate"]) - r["price"]) > 1e-9:
                    diffs.append({"what": "price differs", "name": code, "price_list": r["price_list"],
                                  "shop": p and float(p["price_list_rate"]), "erp": r["price"]})
    return {"since": since, "shop_documents": len(s_inv), "erp_documents": len(e_doc), "still_queued": sorted(still_queued & set(s_inv)),
            "days": days, "differences": diffs, "clean": not diffs,
            "note": "records still queued: stock figures may be transient" if still_queued & set(s_inv) else None}


def main(argv=None):
    p = argparse.ArgumentParser(description="S7 — keep a customer's own system in step with iVendNext")
    p.add_argument("command", choices=("out", "in", "run", "reconcile", "status"))
    p.add_argument("--base", required=True)
    p.add_argument("--app", required=True, help="the Registered Application's name (engine transport)")
    p.add_argument("--erp", default="state/erp.sqlite")
    p.add_argument("--state", default="state/sync.sqlite")
    p.add_argument("--warehouse", required=True)
    p.add_argument("--company", required=True)
    p.add_argument("--since", help="reconcile: only records created at or after this time")
    p.add_argument("--crash-after-out", type=int, help="test only")
    p.add_argument("--crash-after-in", type=int, help="test only")
    p.add_argument("--watch", type=float, help="run: repeat every N seconds")
    a = p.parse_args(argv)
    key, secret = os.environ.get("SYNC_KEY"), os.environ.get("SYNC_SECRET")
    if not key or not secret:
        sys.exit("set SYNC_KEY and SYNC_SECRET in the environment")
    api, erp, store = F.Api(a.base, key, secret), Erp(a.erp), F.Store(a.state)
    init_state(store.db)
    shop, feed = Shop(api, a.warehouse, a.company), F.EngineFeed(api, a.app)
    if a.command in ("out", "in", "run"):
        while True:
            res = {}
            if a.command in ("out", "run"):
                res["out"] = push_out(erp, store.db, shop, a.crash_after_out)
            if a.command in ("in", "run"):
                res["in"] = F.poll(feed, store, make_handler(erp, shop), crash_after=a.crash_after_in)
            print(json.dumps(res), flush=True)
            if not (a.watch and a.command == "run"):
                break
            time.sleep(a.watch)
    elif a.command == "reconcile":
        if not a.since:
            sys.exit("--since is required")
        queued = {d for _t, d in F.queued_docs(feed)}
        print(json.dumps(reconcile(erp, store.db, shop, a.since, queued), default=str))
    else:
        print(json.dumps({"cursor": cursor_of(store.db), "last_change": (erp.db.execute("select max(seq) from changes").fetchone()[0] or 0),
                          "events_seen": store.db.execute("select count(*) from seen").fetchone()[0],
                          "backlog": feed.backlog()}))


if __name__ == "__main__":
    try:
        main()
    except (F.FeedError, RuntimeError) as e:
        sys.exit(f"SYNC_ERROR {e}")
