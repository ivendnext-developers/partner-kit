#!/usr/bin/env python3
"""S39 — *Pharmacy counter rules*: the service behind the till's check before payment (two subscriptions) and the Desk's
document checks (three), standard library only.

    POST /rxc/dispensary       the dispensary's check (``check/1``; declared down answer: refuse)
    POST /rxc/front            the front of the shop's check (``check/1``; allow and flag)
    POST /rxc/desk/order       the document check on Sales Order    (``doccheck/1``, submit)
    POST /rxc/desk/delivery    the document check on Delivery Note  (``doccheck/1``, submit)
    POST /rxc/desk/invoice     the document check on Sales Invoice  (``doccheck/1``, submit)
    GET  /health               200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json ``"runs": "function"``): it only answers presses, and
it keeps nothing between them but a one-minute copy of the shop's settings, schedules, item groups and POS Profiles'
default customers. Every prescription, pharmacist, patient field and dispensing is a record in the shop, read with the
app's integration key; the one record the service writes is its own ``<prefix> Dispensing``.

Each route is checked with ITS OWN secret, the one the install made for that subscription (``<app>:sub:<key>``).

How a sale is decided (``Service.decide``):
1. the shop's settings, schedules and item groups (kept a minute), the lines' items, their schedule rows and units;
2. a sale with no line under a schedule or a group that needs directions is allowed, after releasing any reservation the
   same sale made on an earlier press of Pay;
3. otherwise the operator's Pharmacist record, the customer's identity and consent fields, the named prescriptions and the
   patient's dispensings, each dispensing's status read back from the shop (``rxrules.resolve``);
4. ``rxrules.decide``; on allow, the reservation is inserted as the patient's next number. The name is unique: an insert
   another till made first fails, and the decision is made again from a fresh read (at most ``TRIES`` times);
5. this sale's earlier reservation, and every status the shop gave back, are written (best effort).

When the shop cannot be read, refuses the key, or has not handed over its integration user's key yet, the service
answers 503 and the till applies the subscription's down answer.

ONE SHOP (env or an env file):
    IVN_SECRET_<KEY>   each subscription's secret (handed back at install as pp_rxc:sub:<key>), for the keys
                       DISPENSARY, FRONT, DESK_ORDER, DESK_DELIVERY, DESK_INVOICE
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_rxc), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
RXC_PREFIX (default PP RXC; IVENDNEXT RXC for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

import datetime
import http.client
import json
import os
import signal
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import rxrules  # noqa: E402
import shops  # noqa: E402

KEPT_TTL = 60          # the shop's settings, schedules, item groups and profiles' customers, kept a minute per shop
RESERVE_BY = 4.0       # seconds from the call's arrival: past it the service answers 503 rather than reserve a fill the
                       # till may already have given up on (its 5 s), which would hold the fill until the day closes
READ_TIMEOUT = 2.0     # each read waits at most this (1.0 timed out once on our test bench, a read queued behind
                       # its parallel siblings); the till cuts the whole check at its 5 s and applies the down answer
WRITE_BACK_MAX = 5     # statuses written back per call (the Desk list's words; every decision reads them back anyway)
TRIES = 3              # decide again after another till took the patient's next number first
RECHECK_DAYS = 400     # a dispensing is re-read from the shop this many days (a prescription's life): a cancellation, a
                       # status set by hand
ROWS_MAX = 2000        # a patient's dispensings read per decision (the newest first)
#        route                   (secret key, point)
ROUTES = {"/rxc/dispensary": ("dispensary", "check"),
          "/rxc/front": ("front", "check"),
          "/rxc/desk/order": ("desk_order", "doccheck"),
          "/rxc/desk/delivery": ("desk_delivery", "doccheck"),
          "/rxc/desk/invoice": ("desk_invoice", "doccheck")}
DESK_DOCTYPE = {"desk_order": "Sales Order", "desk_delivery": "Delivery Note", "desk_invoice": "Sales Invoice"}


class ShopUnreadable(Exception):
    pass


class Taken(Exception):
    """Another till took the patient's next dispensing number first."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _q(name: str) -> str:
    return urllib.parse.quote(name, safe="")


class ShopApi:
    """The reads and the one write the service makes, with the shop's own key. Swapped for a stand-in in the tests."""

    def _call(self, url: str, key: str, method: str, path: str, query: dict | None = None, body: dict | None = None,
              missing=False):
        q = f"?{urllib.parse.urlencode(query)}" if query else ""
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(f"{url.rstrip('/')}{path}{q}", data=data, method=method,
                                     headers={"Authorization": f"token {key}", "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=READ_TIMEOUT) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            code = e.code
            e.close()
            if missing and code == 404:
                return None
            if method == "POST" and code == 409:
                raise Taken() from None
            raise ShopUnreadable(f"the shop answered {code}") from None
        except (OSError, http.client.HTTPException, ValueError) as e:   # OSError: URLError, timeouts, TLS, a cut
            raise ShopUnreadable(type(e).__name__) from None             # connection; HTTPException: a cut answer

    @staticmethod
    def _data(out, kind):
        data = out.get("data") if isinstance(out, dict) else None
        if not isinstance(data, kind):
            raise ShopUnreadable("the shop's answer is not records")
        return data

    def get_list(self, url, key, doctype, fields, filters=None, parent=None, order_by=None, limit=0) -> list:
        query = {"fields": json.dumps(fields), "limit_page_length": limit}
        if filters:
            query["filters"] = json.dumps(filters)
        if parent:
            query["parent"] = parent
        if order_by:
            query["order_by"] = order_by
        return self._data(self._call(url, key, "GET", "/api/resource/" + _q(doctype), query), list)

    def get_one(self, url, key, doctype, name):
        out = self._call(url, key, "GET", "/api/resource/" + _q(doctype) + "/" + _q(name), missing=True)
        return None if out is None else self._data(out, dict)

    def insert(self, url, key, doctype, doc: dict) -> dict:
        return self._data(self._call(url, key, "POST", "/api/resource/" + _q(doctype), body=doc), dict)

    def update(self, url, key, doctype, name, values: dict) -> dict:
        return self._data(self._call(url, key, "PUT", "/api/resource/" + _q(doctype) + "/" + _q(name), body=values), dict)


class Service:
    def __init__(self, conf: dict, store=None, api=None, clock=time.monotonic, now=time.time):
        self.prefix = (conf.get("RXC_PREFIX") or "PP RXC").strip()
        self.p = rxrules.field_prefix(self.prefix)
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.api, self.clock, self.now, self.lock = api or ShopApi(), clock, now, threading.Lock()
        self.kept, self.profiles = {}, {}
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secrets = {k: conf[f"IVN_SECRET_{k.upper()}"] for k, _ in ROUTES.values()}
            self.shop = {"url": conf["IVN_SHOP_URL"].rstrip("/"), "key": conf["IVN_SHOP_KEY"]}

    def dt(self, suffix: str) -> str:
        return f"{self.prefix} {suffix}"

    # ── who is calling ────────────────────────────────────────────────────────

    def caller(self, route_key: str, headers) -> tuple[str, list[str], dict | None]:
        """(the shop's name for the caches, the secrets this route's call may be signed with, the shop's address and key)."""
        if not self.app:
            return "-", [self.secrets[route_key]], self.shop
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{route_key}")]
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        shop = {"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None
        return site or "", secrets, shop

    # ── reads ────────────────────────────────────────────────────────────────

    def _list(self, shop, *a, **k):
        return self.api.get_list(shop["url"], shop["key"], *a, **k)

    def basics(self, name: str, shop: dict) -> tuple[dict, dict, dict]:
        """(settings, item groups, schedules), kept KEPT_TTL seconds for this shop and this key."""
        now, key = self.clock(), shop["key"]
        with self.lock:
            hit = self.kept.get(name)
        if hit and hit[1] == key and now - hit[0] < KEPT_TTL:
            return hit[2]
        p = self.p
        with ThreadPoolExecutor(max_workers=3) as pool:
            s = pool.submit(self.api.get_one, shop["url"], key, self.dt("Settings"), "Default")
            g = pool.submit(self._list, shop, "Item Group", ["name", "lft", "rgt", f"{p}_schedule", f"{p}_needs_directions"])
            d = pool.submit(self._list, shop, self.dt("Drug Schedule"), [
                "name", "axis", "needs_prescription", "pharmacist_only", "dispensary_only", "validity_days", "max_fills",
                "qty_cap", "freq_qty", "freq_days", "needs_id_number", "needs_birth_date", "needs_authority", "needs_consent",
                "returnable", "return_gives_back", "needs_directions", "own_sale_without_rx", "max_occasions",
                "one_drug_per_rx"])
            out = (rxrules.settings_of(s.result()), rxrules.groups_of(g.result(), self.prefix),
                   rxrules.schedules_of(d.result()))
        with self.lock:
            self.kept[name] = (now, key, out)
        return out

    def profile_customers(self, name: str, shop: dict) -> set:
        """Every POS Profile's own default customer (each stands for an unnamed sale, at the till and on the Desk), kept
        KEPT_TTL seconds for this shop and this key."""
        now, k = self.clock(), (name, shop["key"])
        with self.lock:
            hit = self.profiles.get(k)
        if hit and now - hit[0] < KEPT_TTL:
            return hit[1]
        custs = {r.get("customer") for r in self._list(shop, "POS Profile", ["name", "customer"]) if r.get("customer")}
        with self.lock:
            if len(self.profiles) > 5000:
                self.profiles.clear()
            self.profiles[k] = (now, custs)
        return custs

    def item_data(self, shop: dict, codes: list, with_units: bool, today) -> tuple[dict, dict, dict]:
        """(items, their schedule rows, their units): one step for the items, a second for the templates of variants."""
        p = self.p
        items, rows, units = {}, {}, {}
        want = sorted(set(codes))
        for _step in range(2):
            if not want:
                break
            with ThreadPoolExecutor(max_workers=3) as pool:
                i = pool.submit(self._list, shop, "Item", ["name", "variant_of", "stock_uom", f"{p}_directions"],
                                [["name", "in", want]])
                r = pool.submit(self._list, shop, self.dt("Item Schedule"), ["parent", "schedule", "effective_from"],
                                [["parent", "in", want]], parent="Item")
                u = pool.submit(self._list, shop, "UOM Conversion Detail", ["parent", "uom", "conversion_factor"],
                                [["parent", "in", want]], parent="Item") if with_units else None
                got = rxrules.items_of(i.result(), self.prefix)
                if set(want) - set(got):
                    raise ShopUnreadable("an item could not be read")
                items.update(got)
                for code, xs in rxrules.item_schedules_of(r.result(), today).items():
                    rows.setdefault(code, []).extend(xs)
                if u:
                    units.update(rxrules.conversions_of(u.result()))
            want = sorted({v["template"] for c, v in items.items() if v["template"] and c not in rows
                           and v["template"] not in items})
        return items, rows, units

    def patient(self, shop: dict, ctx: dict, refs: list, ids: list, today=None) -> dict:
        """The operator's Pharmacist record, WHETHER each identity field this sale needs is filled in (a filter on the
        shop's side: the value never leaves the shop), the named prescriptions and the patient's dispensings (newest
        first), in one parallel step. Each field is asked both ways, set and not set: a shop that answers yes to both
        (a filter it dropped) or no to both is unreadable, never a field read as filled in. A dated field is also asked
        whether its day has come."""
        p, cust = self.p, ctx["customer"]
        on = (today or datetime.date.today()).isoformat()
        asks = {f: {"set": [[f"{p}_{f}", "is", "set"]], "unset": [[f"{p}_{f}", "is", "not set"]],
                    **({"due": [[f"{p}_{f}", "<=", on]]} if f in rxrules.DATED else {})} for f in ids}
        with ThreadPoolExecutor(max_workers=4 + 3 * len(ids)) as pool:
            ph = pool.submit(self._pharmacist_rows, shop, ctx["operator"])
            known = pool.submit(self._list, shop, "Customer", ["name"], [["name", "=", cust]])
            has = {f: {k: pool.submit(self._list, shop, "Customer", ["name"], [["name", "=", cust]] + c) for k, c in a.items()}
                   for f, a in asks.items()}
            rx = pool.submit(self._rx_headers, shop, refs, cust) if refs else None
            disp = pool.submit(self._dispensings, shop, [["customer", "=", cust]])
            if not known.result():
                raise ShopUnreadable("the customer could not be read")
            filled = {}
            for f, js in has.items():
                got = {k: bool(j.result()) for k, j in js.items()}
                if got["set"] == got["unset"]:
                    raise ShopUnreadable("the shop answered a patient field both ways")
                filled[f] = got["set"] and got.get("due", True)
            return {"pharmacist": self._pharmacist(ph.result()), "customer_fields": filled,
                    "rx_headers": rx.result() if rx else [], "dispensings": disp.result()}

    def _pharmacist_rows(self, shop, operator):
        return self._list(shop, self.dt("Pharmacist"), ["name", "user", "active", "valid_until", "delegate"],
                          [["user", "=", operator or "-"]])

    @staticmethod
    def _pharmacist(rows):
        row = next((r for r in rows if rxrules._flag(r.get("active"))), rows[0] if rows else None)
        return {"active": rxrules._flag(row.get("active")), "valid_until": rxrules._date(row.get("valid_until")),
                "delegate": rxrules._flag(row.get("delegate"))} if row else None

    def _rx_headers(self, shop, refs, customer):
        fields = ["name", "reference", "customer", "date_written", "fills_authorised", "retained", "status", "prescriber"]
        by_name = self._list(shop, self.dt("Prescription"), fields, [["name", "in", refs]])
        by_ref = self._list(shop, self.dt("Prescription"), fields, [["reference", "in", refs], ["customer", "=", customer]])
        seen = {r["name"] for r in by_name}
        return by_name + [r for r in by_ref if r["name"] not in seen]

    def _dispensings(self, shop, filters) -> list:
        return self._list(shop, self.dt("Dispensing"), [
            "name", "seq", "status", "source", "sale_ref", "document_type", "document", "pos_opening", "pos_invoice",
            "day", "lines_json", "customer"], filters, order_by="seq desc", limit=ROWS_MAX)

    def shop_states(self, shop: dict, dispensings: list, return_of: str, today) -> tuple[dict, list]:
        """What the shop says about the patient's open dispensings (``rxrules.resolve``'s ``shop``), and the dispensings a
        till return takes back (those of its original sale)."""
        # every reservation, and every dispensing of the last RECHECK_DAYS days whatever its status (a sale cancelled
        # since, a status set by hand): an older one is not looked for, so it stays as it was
        since = today - datetime.timedelta(days=RECHECK_DAYS)
        open_ = [d for d in dispensings if d["status"] == rxrules.RESERVED or d["day"] >= since]
        till = [d for d in open_ if d["source"] != "desk"]
        sale_refs = sorted({d["sale_ref"].strip().lower() for d in till if not any(x["qty"] < 0 for x in d["lines"])})
        return_keys = sorted({d["sale_ref"] for d in till if any(x["qty"] < 0 for x in d["lines"])})
        days = sorted({d["pos_opening"] for d in till if d["pos_opening"]})
        desk: dict = {}
        for d in open_:
            if d["source"] == "desk":
                desk.setdefault(d["document_type"], set()).add(d["document"])
        newest: dict = {}
        for d in dispensings:            # the newest dispensing of each sale or document is the one its booking matches
            if d["sale_ref"] and d["seq"] >= newest.get(d["sale_ref"], (0, ""))[0]:
                newest[d["sale_ref"]] = (d["seq"], d["name"])
        out = {"sales": {}, "returns": {}, "closed_days": set(), "documents": {},
               "newest": {k: v[1] for k, v in newest.items()}}
        jobs = []
        with ThreadPoolExecutor(max_workers=6) as pool:
            if sale_refs:
                jobs.append(("sales", pool.submit(self._list, shop, "POS Invoice", [
                    "name", "docstatus", "custom_mpos_sale_ref"], [["custom_mpos_sale_ref", "in", sale_refs],
                                                                  ["is_return", "=", 0]])))
            if return_keys:
                jobs.append(("returns", pool.submit(self._list, shop, "POS Invoice", [
                    "name", "docstatus", "custom_mpos_idempotency_key"], [["custom_mpos_idempotency_key", "in", return_keys],
                                                                          ["is_return", "=", 1]])))
            if days:
                jobs.append(("days", pool.submit(self._list, shop, "POS Opening Entry", ["name", "status"],
                                                 [["name", "in", days]])))
            for doctype, names in desk.items():
                if doctype in rxrules.DESK_TYPES:
                    jobs.append((f"doc:{doctype}", pool.submit(self._documents, shop, doctype, sorted(names))))
            orig = pool.submit(self._list, shop, "POS Invoice", ["name", "custom_mpos_sale_ref"],
                               [["name", "=", return_of]]) if return_of else None
            for kind, job in jobs:
                rows = job.result()
                if kind == "sales":
                    for r in rows:                                    # a booked sale wins over a cancelled one
                        k = (r.get("custom_mpos_sale_ref") or "").strip().lower()
                        if k not in out["sales"] or r.get("docstatus") == 1:
                            out["sales"][k] = (r["name"], r.get("docstatus"))
                elif kind == "returns":
                    for r in rows:
                        k = r.get("custom_mpos_idempotency_key") or ""
                        if k not in out["returns"] or r.get("docstatus") == 1:
                            out["returns"][k] = (r["name"], r.get("docstatus"))
                elif kind == "days":
                    out["closed_days"] = {r["name"] for r in rows if r.get("status") == "Closed"}
                else:
                    doctype = kind[4:]
                    out["documents"].update({f"{doctype}:{k}": v for k, v in rows.items()})
            orig_rows = orig.result() if orig else []
        out["return_of_ref"] = (orig_rows[0].get("custom_mpos_sale_ref") or "").strip().lower() if orig_rows else ""
        return out, []

    def _documents(self, shop, doctype, names) -> dict:
        """``{name: (docstatus, customer)}`` for the Desk documents a patient's dispensings name. One the list does not
        return is asked for by name: a 404 is gone (``None``); any other refusal means the shop will not show it to the
        app's user (a User Permission), which is never read as gone (``"hidden"``)."""
        rows = {r["name"]: (r.get("docstatus"), r.get("customer"))
                for r in self._list(shop, doctype, ["name", "docstatus", "customer"], [["name", "in", names]])}
        for n in names:
            if n not in rows:
                try:
                    one = self.api.get_one(shop["url"], shop["key"], doctype, n)
                    rows[n] = None if one is None else (one.get("docstatus"), one.get("customer"))
                except ShopUnreadable:
                    rows[n] = ("hidden", None)
        return {k: v for k, v in rows.items() if v is not None}

    # ── the decision ─────────────────────────────────────────────────────────

    def decide(self, name: str, shop: dict | None, ctx: dict, route: str) -> dict:
        if not shop:
            raise ShopUnreadable("the shop has not handed over its integration user's key")
        if not ctx["lines"]:
            return {"verdict": "allow"}
        started = self.clock()
        settings, groups, schedules = self.basics(name, shop)
        today = rxrules.today_at(settings["hours"], self.now())
        codes = [x["item"] for x in ctx["lines"]]
        items, item_rows, units = self.item_data(shop, codes, any(x["uom"] for x in ctx["lines"]), today)
        rules = [rxrules.strictest(rxrules.schedules_for(x["item"], x["group"], items, item_rows, groups, schedules))
                 for x in ctx["lines"]]
        directions = [bool(rxrules.nearest_group(x["group"], groups, lambda row: row[3])) for x in ctx["lines"]]
        if not any(rules) and not any(directions):
            self.release_earlier(shop, ctx, keep=None)
            return {"verdict": "allow"}
        walk = (not ctx["customer"] or ctx["customer"] in settings["walk_ins"]
                or ctx["customer"] in self.profile_customers(name, shop))
        ids = sorted({f for r, x in zip(rules, ctx["lines"]) if r and x["qty"] > 0 for f in r["ids"]})
        refs = rxrules.refs_of(ctx["details"].get(f"{self.prefix} {rxrules.RX}", ""))
        qty = [rxrules.to_stock(x, items, units) for x in ctx["lines"]]
        for attempt in range(TRIES):
            if walk:
                pat = {"pharmacist": None, "customer_fields": {}, "rx_headers": [], "dispensings": []}
                pat["pharmacist"] = self.patient_pharmacist(shop, ctx["operator"])
            else:
                pat = self.patient(shop, ctx, refs, ids, today)
            dispensings = rxrules.dispensings_of(pat["dispensings"])
            states, _ = self.shop_states(shop, dispensings, ctx["return_of"], today) if dispensings else (
                {"sales": {}, "returns": {}, "closed_days": set(), "documents": {}, "newest": {}, "return_of_ref": ""}, [])
            changed = {}
            for d in dispensings:
                new = rxrules.resolve(d, states)
                if new != d["status"]:
                    changed[d["name"]] = new
                    d["status"] = new
            # the dispensings a return takes back: its original sale's (till) or its chain's (Desk), as resolved now
            positive = [d for d in dispensings if d["status"] in (rxrules.RESERVED, rxrules.DISPENSED)
                        and any(x["qty"] > 0 for x in d["lines"])]
            if ctx["source"] == "desk":
                parents = {ctx["return_of"]} | {x.get("parent", "") for x in ctx["lines"]}
                returned_from = [d for d in positive if d["source"] == "desk" and d["document"] in parents]
            else:
                ref = states.get("return_of_ref") or ""
                returned_from = [d for d in positive if d["source"] != "desk" and ref and d["sale_ref"].strip().lower() == ref]
            rx_items = self._list(shop, self.dt("Prescription Item"), ["parent", "item_code", "qty", "directions"],
                                  [["parent", "in", [r["name"] for r in pat["rx_headers"]]]],
                                  parent=self.dt("Prescription")) if pat["rx_headers"] else []
            data = {"rules": rules, "qty": qty, "items": items, "group_directions": directions, "walk_in": walk,
                    "pharmacist": pat["pharmacist"], "customer_fields": pat["customer_fields"],
                    "rxs": rxrules.prescriptions_of(pat["rx_headers"], rx_items), "dispensings": dispensings,
                    "returned_from": returned_from}
            answer = rxrules.decide(ctx, route, data, today, self.prefix)
            keep = None
            if answer["verdict"] == "allow" and answer.get("record"):
                mine = [d for d in dispensings if d["sale_ref"] == ctx["sale_ref"] and d["status"] == rxrules.RESERVED]
                keep = next((d["name"] for d in mine if rxrules.same_record(d, answer["record"])), None)
                if not keep:
                    if self.clock() - started > RESERVE_BY:
                        raise ShopUnreadable("too late to reserve")
                    try:
                        keep = self.reserve(shop, ctx, dispensings, answer["record"], today)
                    except Taken:
                        continue                         # another till took the number: read again, decide again
            self.release_earlier(shop, ctx, keep=keep)
            self.write_back(shop, dict(list(changed.items())[:WRITE_BACK_MAX]))
            answer.pop("record", None)
            return answer
        raise ShopUnreadable("the patient's next dispensing number stayed taken")

    def patient_pharmacist(self, shop, operator):
        return self._pharmacist(self._pharmacist_rows(shop, operator))

    def reserve(self, shop: dict, ctx: dict, dispensings: list, record: dict, today) -> str:
        """Insert the patient's next dispensing (``Taken`` when another till took the number)."""
        name, seq = rxrules.next_name(ctx["customer"], dispensings)
        give_back = any(x["qty"] < 0 for x in record["lines"])
        doc = {"key": name, "seq": seq, "customer": ctx["customer"], "status": rxrules.RESERVED,
               "source": ctx["source"], "sale_ref": ctx["sale_ref"], "pos_opening": ctx["pos_opening"],
               "document_type": ctx["doctype"], "document": ctx["name"], "day": today.isoformat(),
               "operator": ctx["operator"], "give_back": 1 if give_back else 0,
               "prescription": next((x["rx"] for x in record["lines"] if x.get("rx")), ""),
               "lines_json": json.dumps({"lines": record["lines"], "fingerprints": record["fingerprints"]}),
               "summary": rxrules.summary(record["lines"])}
        self.api.insert(shop["url"], shop["key"], self.dt("Dispensing"), doc)
        return name

    def write_back(self, shop: dict, changed: dict) -> None:
        """Each status the shop gave back, written on its dispensing so the Desk list reads it (best effort: the next
        decision reads it back again)."""
        for name, status in changed.items():
            try:
                self.api.update(shop["url"], shop["key"], self.dt("Dispensing"), name, {"status": status})
            except (ShopUnreadable, Taken):
                pass

    def release_earlier(self, shop: dict, ctx: dict, keep: str | None) -> None:
        """This sale's (or document's) earlier reservations, made on an earlier press of Pay or an earlier submit, other
        than the one kept: released (best effort). Read by the sale's reference, whoever the customer was then."""
        if not ctx["sale_ref"]:
            return
        try:
            rows = rxrules.dispensings_of(
                self._dispensings(shop, [["sale_ref", "=", ctx["sale_ref"]], ["status", "=", rxrules.RESERVED]]))
        except (ShopUnreadable, ValueError):
            return
        for d in rows:
            if d["sale_ref"] == ctx["sale_ref"] and d["status"] == rxrules.RESERVED and d["name"] != keep:
                try:
                    self.api.update(shop["url"], shop["key"], self.dt("Dispensing"), d["name"], {"status": rxrules.RELEASED})
                except (ShopUnreadable, Taken):
                    pass

    # ── the call ─────────────────────────────────────────────────────────────

    def answer(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if path not in ROUTES:
            return 404, {"error": "not found"}
        route_key, point = ROUTES[path]
        try:
            name, secrets, shop = self.caller(route_key, headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(rxrules.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            ctx = rxrules.sale_context(body) if point == "check" else rxrules.desk_context(body, self.prefix)
            if point == "doccheck" and ctx["doctype"] != DESK_DOCTYPE[route_key]:
                raise ValueError("this route checks another record type")
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if point == "doccheck" and ctx["event"] != "submit":
            return 200, {"verdict": "allow"}            # a draft's save is never judged
        route = route_key if point == "check" else "desk"
        try:
            return 200, self.decide(name, shop, ctx, route)
        except (ShopUnreadable, ValueError) as e:       # the shop did not answer, or not with records: nothing was judged
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "the shop cannot be read"}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > rxrules.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.answer(path, headers, raw)


def _log(log, rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a secret or a signature."""
    log.write(json.dumps({"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
    log.flush()


def make_server(svc: Service, port: int, log=sys.stdout):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            t0, rid, code = time.monotonic(), (self.headers.get("X-iVendNext-Request-Id") or "-")[:40], 500
            try:
                n = int(self.headers.get("Content-Length") or 0)
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= rxrules.BODY_MAX else None)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the framework's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b): settings from the environment.
lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle)


def env_file(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env_file(sys.argv[1]) if len(sys.argv) > 1 else {}))
    one = [f"IVN_SECRET_{k.upper()}" for k, _ in ROUTES.values()] + ["IVN_SHOP_URL", "IVN_SHOP_KEY"]
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in one)):
        raise SystemExit("set " + ", ".join(one) + " (one shop), or IVN_LIBRARY_APP with a store (many shops): "
                         "the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
