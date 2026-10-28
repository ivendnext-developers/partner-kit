#!/usr/bin/env python3
"""S43 — *Third-party payer*: the payer service the POS app's payer door calls (``payer/1``), and six Desk buttons
for the claims clerk (standard library only).

    POST /icp/payer            the payer door's two calls, ``covers`` and ``coverage`` (``payer/1``: the POS app's
                               docs/extending/payer.md and its contract, contracts/extension_contracts/payer.v1.schema.json)
    POST /icp/press/claims     Desk button *Build claims* on the Payer list (``desk_action/1``): reads the event feed's
                               booked sales and returns once, and makes or reduces each sale's claim
    POST /icp/press/file       Desk button *Make the claims file* on a Payer (``desk_action/1``): every Ready claim of
                               that payer into one Claim Batch (a CSV), each then Submitted (Resubmitted if corrected)
    POST /icp/press/remit      Desk button *Match* on a Remittance (``desk_action/1``): each line against its claim
    POST /icp/press/ready      Desk button *Mark ready* on a Claim: Ready once complete (a corrected rejection goes again)
    POST /icp/press/settle     Desk button *Settle as it stands* on a short-paid Claim: Paid, the shortfall left
    POST /icp/press/billback   Desk button *Bill to the customer* on a rejected or short-paid Claim (``desk_action/1``):
                               the payer door's ``payer_bill_back`` moves what the payer did not pay back to the
                               customer, on their own sale (payer.md §4c)
    GET  /health               200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

It runs as a FUNCTION (app.json ``"runs": "function"``): it only answers calls and presses and keeps nothing between
them. Every payer, plan, formulary, member and claim is a record in the shop, read and written with the app's
integration key. ⚠ Members and claims are health data for a pharmacy: run it in the shop's own region (Pharmacy
``PH-D21``), and never send a claims file anywhere but to the payer.

Each route is checked with ITS OWN secret, the one the install made for that subscription (``<app>:sub:<key>``).

ONE SHOP (env or an env file):
    IVN_SECRET_<KEY>   each subscription's secret, for the keys PAYER, CLAIMS, FILE, REMIT, READY, SETTLE, BILLBACK (a route
                       without its secret refuses every call)
    IVN_SHOP_URL       the shop's address · IVN_SHOP_KEY  the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS: IVN_LIBRARY_APP (ivendnext_icp) with IVN_SHOPS_TABLE or IVN_SHOPS_FILE (tools/app_template/service/shops.py)
ICP_PREFIX (default PP ICP; IVENDNEXT ICP for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
sys.path.append(os.path.join(KIT, "tools", "feed_client"))
import claims as K  # noqa: E402
import copay as C  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

BODY_MAX = 256 * 1024
REFUSAL_MAX = 250       # the door's words in a press's answer, whose body the door takes up to 280 characters
SKEW_S = 300
READ_TIMEOUT = 2.0      # the door waits at most 5 s for an answer; each read here waits at most this
ANSWER_BY = 4.0         # past it the service answers 503 (the door says the payer cannot be reached) rather than late
FEED_PAGE = 50          # events read per press of *Build claims*; a press past PRESS_BY seconds stops and says so
PRESS_BY = 8.0
LINES_MAX = 200
#        route                   (secret key, point)
ROUTES = {"/icp/payer": ("payer", "payer"),
          "/icp/press/claims": ("claims", "desk_action"),
          "/icp/press/file": ("file", "desk_action"),
          "/icp/press/remit": ("remit", "desk_action"),
          "/icp/press/ready": ("ready", "desk_action"),
          "/icp/press/settle": ("settle", "desk_action"),
          "/icp/press/billback": ("billback", "desk_action")}
NOW = ("payer", "claims", "file", "remit", "ready", "settle", "billback")      # the subscriptions this version installs
DOOR_METHOD = "/api/method/ivendnext_mpos.api.v1.payer_bill_back"
# What the payer door stores on a sale and its lines (payer.md §4b; a return's give-back, §4c). A payer service reads
# them through the event feed.
DOOR = {"payer": "custom_mpos_payer_code", "plan": "custom_mpos_payer_plan", "member": "custom_mpos_payer_member",
        "claim_ref": "custom_mpos_payer_claim_ref", "prescription": "custom_mpos_payer_prescription",
        "prescriber": "custom_mpos_payer_prescriber", "prescriber_licence": "custom_mpos_payer_prescriber_licence",
        "line_payer": "custom_mpos_payer_share", "line_patient": "custom_mpos_patient_share",
        "line_qty": "custom_mpos_payer_covered_qty", "line_gtin": "custom_mpos_payer_gtin",
        "line_back": "custom_mpos_payer_back", "journal": "custom_mpos_payer_journal"}
NO_END = "9999-12-31"   # a cover with no end date: the door takes a date
SALES = {"sale.booked": "POS Invoice", "return.booked": "POS Invoice", "invoice.booked": "Sales Invoice"}


class ShopUnreadable(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _q(name: str) -> str:
    return urllib.parse.quote(name, safe="")


def verify(timestamp: str | None, signature: str | None, raw: bytes, secret: str, now: float | None = None) -> str:
    """``""`` when the request is the shop's, else why not: base64 HMAC-SHA256 of ``<timestamp>.<raw body>``."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return "the request's time is missing or too far from ours"
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    return "" if hmac.compare_digest(want, sig.encode()) else "the signature does not match"


def _message(body: str, level: str = "info") -> dict:
    return {"message": {"title": "Third-party payer", "body": body, "level": level}, "refresh": True}


class ShopApi:
    """The shop's record API with the app's own key. Swapped for a stand-in in the tests."""

    def _call(self, url, key, method, path, query=None, body=None, missing=False, refusal=False):
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
            if not (refusal and code == 417):
                e.close()
            if missing and code == 404:
                return None
            if method == "POST" and code == 409:
                return {"duplicate": True}
            if refusal and code == 417:
                return {"refused": _refusal(e)}
            raise ShopUnreadable(f"the shop answered {code}") from None
        except (OSError, http.client.HTTPException, ValueError) as e:
            raise ShopUnreadable(type(e).__name__) from None

    def get_list(self, url, key, doctype, fields, filters=None, limit=0) -> list:
        query = {"fields": json.dumps(fields), "limit_page_length": limit}
        if filters:
            query["filters"] = json.dumps(filters)
        out = self._call(url, key, "GET", "/api/resource/" + _q(doctype), query)
        if not isinstance(out.get("data"), list):
            raise ShopUnreadable("the shop's answer is not records")
        return out["data"]

    def get_one(self, url, key, doctype, name):
        out = self._call(url, key, "GET", "/api/resource/" + _q(doctype) + "/" + _q(name), missing=True)
        return None if out is None else out.get("data")

    def insert(self, url, key, doctype, doc):
        return self._call(url, key, "POST", "/api/resource/" + _q(doctype), body=doc)

    def update(self, url, key, doctype, name, values):
        return self._call(url, key, "PUT", "/api/resource/" + _q(doctype) + "/" + _q(name), body=values)

    def feed(self, url, key, call, body):
        """The event feed's door (tools/feed_client's DoorFeed: events · done · failed, each a POST)."""
        return (self._call(url, key, "POST", f"/api/method/ivendnext_mpos.api.feed.{call}", body=body) or {}).get(
            "message") or {}

    def bill_back(self, url, key, body):
        """The payer door's bill-back (payer.md §4c). None when the shop's POS app has no such door yet."""
        out = self._call(url, key, "POST", DOOR_METHOD, body=body, missing=True, refusal=True)
        return None if out is None else out if "refused" in out else (out.get("message") or {})


def _refusal(err) -> str:
    """The door's own words when it refuses a bill-back (a 417 whose body carries the shop's messages)."""
    try:
        raw = json.loads(err.read(BODY_MAX) or b"{}")
        msgs = json.loads(raw.get("_server_messages") or "[]")
        text = json.loads(msgs[0]).get("message") if msgs else raw.get("exception")
    except (ValueError, TypeError, AttributeError, IndexError, OSError, http.client.HTTPException):
        text = None
    finally:
        err.close()
    return str(text or "The payer door refused it.")[:REFUSAL_MAX]


class Service:
    def __init__(self, conf: dict, store=None, api=None, now=time.time):
        self.prefix = (conf.get("ICP_PREFIX") or "PP ICP").strip()
        self.fp = self.prefix.lower().replace(" ", "_") + "_"
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.api, self.now, self.local = api or ShopApi(), now, threading.local()
        if self.app:
            self.store = store or shops.open_store(conf)
        else:
            self.secrets = {k: conf.get(f"IVN_SECRET_{k.upper()}") for k, _ in ROUTES.values()}
            self.shop = {"url": conf["IVN_SHOP_URL"].rstrip("/"), "key": conf["IVN_SHOP_KEY"]}

    def dt(self, suffix: str) -> str:
        return f"{self.prefix} {suffix}"

    def caller(self, route_key, headers):
        if not self.app:
            return [s for s in [self.secrets[route_key]] if s], self.shop
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{route_key}")]
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        return secrets, ({"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None)

    def _late(self):
        t0 = getattr(self.local, "t0", None)       # per call: the web server answers calls on threads
        if t0 is not None and time.monotonic() - t0 > ANSWER_BY:
            raise ShopUnreadable("too slow")

    def _list(self, shop, *a, **k):
        self._late()
        return self.api.get_list(shop["url"], shop["key"], *a, **k)

    def _one(self, shop, doctype, name):
        self._late()
        return self.api.get_one(shop["url"], shop["key"], doctype, name) if name else None

    def today(self) -> str:
        return datetime.date.fromtimestamp(self.now()).isoformat()

    # ── payer/1 ──────────────────────────────────────────────────────────────

    def barred(self, shop, customer) -> bool:
        rows = self._list(shop, "Customer", ["name", f"{self.fp}insurance_barred"], [["name", "=", customer]])
        return bool(rows and int(rows[0].get(f"{self.fp}insurance_barred") or 0))

    def covers(self, shop, body) -> dict:
        """Every cover the customer holds today, in the shape the door takes (a cover the door could not book, with no
        payer customer or the sale's own customer as the payer, is left out)."""
        customer, today = str(body.get("customer") or ""), str(body.get("date") or self.today())
        if not customer:
            raise ValueError("no customer")
        if self.barred(shop, customer):
            return {"covers": [], "refused": {"code": "barred",
                                              "message": C.WORDS["barred"].format(customer=customer, payer="a payer")}}
        members = self._list(shop, self.dt("Member"), ["name", "plan", "payer", "member_number", "valid_from",
                                                         "valid_to", "active"], [["customer", "=", customer]])
        out = []
        for m in members:
            plan = self._one(shop, self.dt("Plan"), m.get("plan"))
            payer = self._one(shop, self.dt("Payer"), (plan or {}).get("payer"))
            if not (plan and payer and all(C._in_force(r, today) for r in (m, plan, payer))) or \
                    not payer.get("customer") or payer["customer"] == customer or \
                    not self.billable(shop, payer["customer"]):
                continue
            num = str(m.get("member_number") or "")
            ends = [str(r["valid_to"]) for r in (m, plan, payer) if r.get("valid_to")]
            out.append({"member": m["name"], "payer": payer["name"],
                        "payer_title": C.plain(payer.get("title")) or payer["name"],
                        "payer_customer": payer["customer"], "plan": plan["name"],
                        "plan_title": C.plain(plan.get("title")) or plan["name"], "member_label": "…" + num[-4:],
                        "valid_to": min(ends) if ends else NO_END, "price_list": plan.get("price_list") or None,
                        "promotions_apply": bool(int(plan.get("promotions_apply", 1) or 0))})
        return {"covers": out[:10], "refused": None}

    def billable(self, shop, name) -> bool:
        """The payer's own Customer record exists and is in use: the door refuses the WHOLE covers answer otherwise."""
        rows = self._list(shop, "Customer", ["name", "disabled"], [["name", "=", name]])
        return bool(rows) and not int(rows[0].get("disabled") or 0)

    def coverage(self, shop, body) -> dict:
        lines = body.get("lines")
        if not isinstance(lines, list) or not 1 <= len(lines) <= LINES_MAX:
            raise ValueError("one to 200 lines")
        customer = str(body.get("customer") or "")
        if not isinstance(body.get("currency_exponent"), int) or not all(
                isinstance(body.get(k), int) and not isinstance(body.get(k), bool) for k in ("total_minor",
                                                                                         "rounding_minor")):
            raise ValueError("the sale's money is whole minor units")
        for l in lines:
            if not isinstance(l, dict) or not all(isinstance(l.get(k), int) and not isinstance(l.get(k), bool)
                                                  for k in ("amount_minor", "discount_minor", "rate_minor")):
                raise ValueError("each line's money is whole minor units")
        if len({l.get("line_id") for l in lines}) != len(lines):
            raise ValueError("each line has its own line_id")
        if sum(l["amount_minor"] for l in lines) != body["total_minor"]:
            raise ValueError("the lines do not add up to the sale's total")
        body = dict(body, date=body.get("date") or self.today())
        member = self._one(shop, self.dt("Member"), body.get("member"))
        if member and member.get("customer") != customer:
            member = None                                   # a member reference of another customer is no cover
        plan = self._one(shop, self.dt("Plan"), (member or {}).get("plan"))
        payer = self._one(shop, self.dt("Payer"), (plan or {}).get("payer"))
        if plan:
            form = self._one(shop, self.dt("Formulary"), plan.get("formulary"))
            plan = dict(plan, formulary=(form or {}).get("rows") or [])
            if plan.get("price_list"):
                plan["currency"] = (self._one(shop, "Price List", plan["price_list"]) or {}).get("currency")
            codes = sorted({str(l.get("item_code")) for l in lines if l.get("item_code")})
            missing_groups = [c for c in codes if not any(l.get("item_code") == c and l.get("item_group")
                                                          for l in lines)]
            if missing_groups:
                groups = {r["name"]: r["item_group"] for r in self._list(
                    shop, "Item", ["name", "item_group"], [["name", "in", missing_groups]])}
                for l in lines:
                    if not l.get("item_group"):        # the door sends an empty group as ""
                        l["item_group"] = groups.get(l.get("item_code"))
        prices = self.list_prices(shop, plan, lines, body["date"], customer) if plan and plan.get("price_list") else None
        return C.door_coverage(body, plan, member, self.barred(shop, customer), prices, payer)

    def list_prices(self, shop, plan, lines, today, customer) -> dict:
        """{line_id: that line's price on the plan's list today, or None}: read from the list itself, never from the
        line. A row counts for a line only as the engine applies it: in force today, for no other customer, for no
        batch (a batch's own price is not the list's), and in the line's unit, or else in the item's stock unit times
        the line's conversion factor, or in no unit."""
        codes = sorted({str(l.get("item_code")) for l in lines if l.get("item_code")})
        stock = {r["name"]: r.get("stock_uom") for r in self._list(shop, "Item", ["name", "stock_uom"],
                                                                     [["name", "in", codes]])}
        rows = self._list(shop, "Item Price", ["item_code", "uom", "customer", "batch_no", "price_list_rate",
                                               "valid_from", "valid_upto"],
                          [["price_list", "=", plan["price_list"]], ["item_code", "in", codes]])
        out = {}
        for l in lines:
            best = None
            for r in rows:
                if r["item_code"] != l.get("item_code") or r.get("batch_no") or \
                        (r.get("customer") and r["customer"] != customer) or \
                        (r.get("valid_from") and r["valid_from"] > today) or \
                        (r.get("valid_upto") and r["valid_upto"] < today):
                    continue
                rate = C.D(r.get("price_list_rate"))
                if not r.get("uom") or not l.get("uom") or r["uom"] == l["uom"]:
                    rank = 2 if r.get("uom") and r["uom"] == l.get("uom") else 0
                elif r["uom"] == stock.get(l.get("item_code")):
                    rank, rate = 1, rate * (C.D(l.get("conversion_factor")) or C.Decimal(1))
                else:
                    continue                                 # another unit, neither the line's nor the stock unit
                if best is None or rank > best[0]:
                    best = (rank, rate)
            out[l.get("line_id")] = None if best is None else best[1]
        return out

    # ── claims from booked sales (the event feed) ────────────────────────────

    def payer_sale(self, doc: dict, doctype: str) -> dict | None:
        """The door's record of a sale (payer.md §4b), or None when no payer leg was booked on it."""
        if not doc.get(DOOR["claim_ref"]) or not doc.get(DOOR["payer"]):
            return None
        if not int(doc.get("is_return") or 0) and not doc.get(DOOR["journal"]):
            return None         # its booking was cancelled with its day's closing: no claim, nothing owed (payer.md §4b)
        if doctype == "Sales Invoice" and (doc.get("is_consolidated") or any(
                it.get("pos_invoice") for it in doc.get("items") or [])):
            return None         # the till sale's own posting: its claim is the POS sale's, made from that record
        lines = [{"line_id": it.get("name"), "item_code": it.get("item_code"), "gtin": it.get(DOOR["line_gtin"]) or it.get("barcode") or None,
                  "qty": it.get(DOOR["line_qty"]) or it.get("qty"), "uom": it.get("uom"),
                  "amount": str(C.D(it.get(DOOR["line_payer"])) + C.D(it.get(DOOR["line_patient"]))),
                  "payer_share": it.get(DOOR["line_payer"]), "patient_share": it.get(DOOR["line_patient"]),
                  "payer_back": it.get(DOOR["line_back"]), "returned_line": it.get("pos_invoice_item")
                  or it.get("sales_invoice_item"), "back_qty": abs(C.D(it.get("qty")))} for it in doc.get("items") or []]
        return {"doctype": doctype, "name": doc["name"], "posting_date": doc.get("posting_date"),
                "store": doc.get("set_warehouse") or (doc.get("items") or [{}])[0].get("warehouse"),
                "customer": doc.get("customer"), "is_return": int(doc.get("is_return") or 0),
                "return_against": doc.get("return_against"), "lines": lines,
                **{k: doc.get(DOOR[k]) for k in ("payer", "plan", "member", "claim_ref", "prescription", "prescriber",
                                                 "prescriber_licence")}}

    def build_claims(self, shop) -> dict:
        """One press: the feed's events, each handled once (a claim's name is its reference, so a second insert is a
        duplicate the shop refuses), then marked done."""
        t0, made, reduced, skipped, failed = time.monotonic(), 0, 0, 0, 0
        ours = {r["name"] for r in self._list(shop, self.dt("Payer"), ["name"])}
        page = None
        while time.monotonic() - t0 < PRESS_BY:
            got = self.api.feed(shop["url"], shop["key"], "events", {"limit": FEED_PAGE} | ({"page": page} if page
                                                                                              else {}))
            events, page = got.get("events") or [], got.get("page")
            if not events:
                break
            done = []
            for ev in events:
                doctype = SALES.get(ev.get("event"))
                try:
                    if doctype and ev.get("doc_type") == doctype:
                        r = self.handle_sale(shop, doctype, ev.get("doc_name"), ours)
                        made, reduced, skipped = made + (r == "made"), reduced + (r == "reduced"), skipped + (r == "-")
                    done.append(ev["id"])
                except (ShopUnreadable, KeyError, ValueError) as e:
                    failed += 1
                    self.api.feed(shop["url"], shop["key"], "failed", {"id": ev.get("id"), "error": type(e).__name__})
            self.api.feed(shop["url"], shop["key"], "done", {"ids": done})
            if not page:
                break
        more = " More sales are waiting: press again." if time.monotonic() - t0 >= PRESS_BY else ""
        return {"made": made, "reduced": reduced, "not_ours": skipped, "failed": failed, "more": bool(more),
                "text": f"{made} claims made, {reduced} reduced by returns, {failed} failed.{more}"}

    def handle_sale(self, shop, doctype, name, ours) -> str:
        sale = self.payer_sale(self._one(shop, doctype, name) or {}, doctype)
        if not sale or sale["payer"] not in ours:
            return "-"
        if sale["is_return"]:
            claim = self._one(shop, self.dt("Claim"), sale["claim_ref"])
            if not claim:                                   # its sale's claim is not made yet: the feed tries again
                raise ValueError("the return's claim is not made yet")
            if name in (claim.get("returns") or "").split("\n"):
                return "-"                                  # handled before: a return reduces its claim once
            held = {l.get("line_id") for l in claim.get("lines") or []}
            if any(l.get("returned_line") not in held and C.D(l.get("payer_back")) for l in sale["lines"]):
                raise ValueError("a returned line is not on its claim")
            split = {"lines": [{"line_id": l["returned_line"], "qty": str(l["back_qty"]),
                                "payer_back": str(abs(C.D(l["payer_back"])))} for l in sale["lines"]
                               if l.get("returned_line")]}
            claim["lines"] = [dict(l, line_id=l.get("line_id")) for l in claim.get("lines") or []]
            K.apply_return(claim, split)
            self.api.update(shop["url"], shop["key"], self.dt("Claim"), claim["name"], {
                "payer_share": claim["payer_share"], "status": claim["status"],
                "returns": "\n".join(filter(None, [claim.get("returns"), name])),
                "lines": K.rows(claim["lines"])})
            return "reduced"
        payer = self._one(shop, self.dt("Payer"), sale["payer"]) or {}
        member = self._one(shop, self.dt("Member"), sale["member"]) or {}
        claim = K.build_claim(sale, payer, member)
        doc = {k: v for k, v in claim.items() if k != "name"}
        doc["lines"] = [{k: l.get(k) for k in ("line_id", "item_code", "gtin", "qty", "uom", "amount", "payer_share",
                                               "patient_share", "dose", "frequency")} for l in claim["lines"]]
        out = self.api.insert(shop["url"], shop["key"], self.dt("Claim"), doc)
        if out.get("duplicate"):
            held = self._one(shop, self.dt("Claim"), claim["claim_ref"]) or {}
            if held.get("sale") != name:      # two sales, one reference: never filed silently under the first
                raise ValueError("a claim reference another sale already holds")
            return "-"
        return "made"

    # ── the claims file, and a remittance ────────────────────────────────────

    def make_file(self, shop, payer_name) -> dict:
        payer = self._one(shop, self.dt("Payer"), payer_name)
        if not payer:
            raise ValueError("no such payer")
        names = [r["name"] for r in self._list(shop, self.dt("Claim"), ["name"],
                                               [["payer", "=", payer_name], ["status", "in", [K.READY, K.INCOMPLETE]]])]
        claims, gone = [], []
        for c in filter(None, (self._one(shop, self.dt("Claim"), n) for n in names)):
            (claims if self.sale_stands(shop, c) else gone).append(c)
        for c in gone:          # its sale was cancelled since the claim was built: nothing is owed (payer.md §4b)
            K.move(c, K.RETURNED)
            for l in c.get("lines") or []:
                l["payer_back"], l["payer_share"] = l.get("payer_share"), "0"
            self.api.update(shop["url"], shop["key"], self.dt("Claim"), c["name"],
                            {"status": c["status"], "payer_share": "0", "lines": K.rows(c.get("lines") or [])})
        claims = [c for c in claims if c["status"] == K.READY]
        out_text = f" {len(gone)} taken out: their sale was cancelled." if gone else ""
        if not claims:
            return {"text": f"No claim of {payer.get('title') or payer_name} is ready.{out_text}"}
        text = K.claims_file(claims, {"code": payer_name})
        total = sum((C.D(c["payer_share"]) for c in claims), C.ZERO)
        batch = self.api.insert(shop["url"], shop["key"], self.dt("Claim Batch"), {
            "payer": payer_name, "made_on": self.today(), "claims": len(claims), "payer_share": str(total),
            "csv": text})
        bname = (batch.get("data") or {}).get("name")
        for c in claims:
            self.api.update(shop["url"], shop["key"], self.dt("Claim"), c["name"],
                            {"status": K.filed_as(c), "batch": bname, "submitted_on": self.today()})
        return {"text": f"{len(claims)} claims in {bname}, {total} to claim. Send its file to the payer.{out_text}",
                "batch": bname}

    def sale_stands(self, shop, claim) -> bool:
        """The claim's sale is still booked with its payer journal: cancelled since, it owes the payer nothing."""
        doc = self._one(shop, claim.get("sale_doctype") or "POS Invoice", claim.get("sale"))
        return bool(doc) and int(doc.get("docstatus") or 0) == 1 and bool(doc.get(DOOR["journal"]))

    def match(self, shop, remit_name) -> dict:
        """A payer's remittance against its claims: every line of one claim summed first, then settled once."""
        remit = self._one(shop, self.dt("Remittance"), remit_name)
        if not remit:
            raise ValueError("no such remittance")
        rows = remit.get("lines") or []
        per, unknown = {}, 0
        for r in rows:
            per.setdefault(r.get("claim_ref"), []).append(r)
        for ref, mine in per.items():
            c = self._one(shop, self.dt("Claim"), ref)
            if not c or c.get("payer") != remit.get("payer"):   # an unknown reference, or another payer's claim
                for r in mine:
                    r.update(expected="0", result="Unmatched")
                unknown += len(mine)
                continue
            due = C.D(c["payer_share"]) - C.D(c.get("received"))
            result = K.settle(c, sum((C.D(r.get("paid")) for r in mine), C.ZERO),
                              all(r.get("rejected") for r in mine),
                              next((r.get("reason") for r in mine if r.get("reason")), None))
            for r in mine:
                r.update(expected=str(due), result=result)
            self.api.update(shop["url"], shop["key"], self.dt("Claim"), c["name"], {
                k: c.get(k) for k in ("status", "received", "rejection_reason")})
        self.api.update(shop["url"], shop["key"], self.dt("Remittance"), remit_name, {
            "status": "Matched" if not unknown else "Partly matched", "lines": K.rows(rows)})
        return {"text": f"{len(rows) - unknown} of {len(rows)} lines matched."}

    def move_claim(self, shop, claim_name, to) -> dict:
        """The clerk's two moves (a claim's status is never typed): Ready once complete (a rejected one corrected goes
        again as Resubmitted), or a short-paid claim settled as it stands."""
        c = self._one(shop, self.dt("Claim"), claim_name)
        if not c:
            raise ValueError("no such claim")
        if to == K.PAID and c["status"] != K.SHORT:
            return {"text": "Only a short-paid claim is settled as it stands.", "level": "warning"}
        payer = self._one(shop, self.dt("Payer"), c.get("payer")) or {}
        try:
            K.move(c, to, payer=payer)
        except ValueError as e:
            return {"text": str(e), "level": "warning"}
        self.api.update(shop["url"], shop["key"], self.dt("Claim"), c["name"],
                        {k: c.get(k) for k in ("status", "resubmissions", "incomplete_reason")} |
                        ({"incomplete_reason": ""} if to == K.READY else {}))
        return {"text": f"{c['name']} is {c['status']}."}

    def bill_back(self, shop, claim_name) -> dict:
        """What the payer did not pay, owed by the customer again (FR-K4-05): the door books it, then the claim says so."""
        c = self._one(shop, self.dt("Claim"), claim_name)
        if not c:
            raise ValueError("no such claim")
        try:
            K.move(c, K.BILLED)                             # refuses a claim the flow does not allow, or nothing due
        except ValueError as e:
            return {"text": str(e), "level": "warning"}
        got = self.api.bill_back(shop["url"], shop["key"], {"sale": c.get("sale"), "claim_ref": c["claim_ref"],
                                                           "amount": c["billed_back"], "reason": "claim not paid"})
        if got is None:
            return {"text": "Your POS app has no payer door yet: nothing was billed.", "level": "warning"}
        if got.get("refused"):                              # the door's own words: e.g. bill it back after the day's close
            return {"text": f"Nothing was billed: {got['refused']}", "level": "warning"}
        if not got.get("journal"):                          # the door names the journal it booked, or nothing was
            return {"text": "The payer door booked nothing: the claim is unchanged.", "level": "warning"}
        self.api.update(shop["url"], shop["key"], self.dt("Claim"), c["name"],
                        {"status": c["status"], "billed_back": c["billed_back"]})
        return {"text": f"{c['billed_back']} is owed by the customer again, on their own sale."}

    # ── the calls ────────────────────────────────────────────────────────────

    def answer(self, path, headers, raw) -> tuple[int, dict]:
        if path not in ROUTES:
            return 404, {"error": "not found"}
        route_key, point = ROUTES[path]
        try:
            secrets, shop = self.caller(route_key, headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}
        try:
            body = json.loads(raw)
            if not isinstance(body, dict):
                raise ValueError("not an object")
            if point == "desk_action":
                ctx = body.get("context") if body.get("point") == "desk_action/1" else None
                recs = (ctx or {}).get("records")
                if not isinstance(recs, list) or not recs or not isinstance(recs[0], dict):
                    raise ValueError("no records")
            else:
                ctx = body.get("context") if body.get("point") == C.CONTRACT else None
                if not isinstance(ctx, dict) or ctx.get("v") != 1 or ctx.get("point") != "payer" or \
                        ctx.get("call") not in ("covers", "coverage"):
                    raise ValueError("not a payer/1 call")
        except ValueError as e:
            return 400, {"error": str(e)}
        if shop is None:
            return (200, _message("Choose the app's user on its feed, then press Connect again.", "warning")) \
                if point == "desk_action" else (503, {"error": "not set up"})
        try:
            self.local.t0 = time.monotonic() if point == "payer" else None
            if point == "payer":
                return 200, (self.covers(shop, ctx) if ctx["call"] == "covers" else self.coverage(shop, ctx))
            name = recs[0].get("name") or ""
            if route_key == "claims":
                return 200, _message(self.build_claims(shop)["text"])
            if route_key == "file":
                return 200, _message(self.make_file(shop, name)["text"])
            if route_key in ("ready", "settle"):
                out = self.move_claim(shop, name, K.READY if route_key == "ready" else K.PAID)
                return 200, _message(out["text"], out.get("level", "info"))
            if route_key == "billback":
                out = self.bill_back(shop, name)
                return 200, _message(out["text"], out.get("level", "info"))
            return 200, _message(self.match(shop, name)["text"])
        except ValueError as e:
            return 400, {"error": str(e)}
        except ShopUnreadable as e:
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "the shop cannot be read"}

    def handle(self, method, path, headers, raw) -> tuple[int, dict]:
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.answer(path, headers, raw)


def _log(log, rid, path, code, t0):
    """One line per call: never the body, a member number, a secret or a signature."""
    log.write(json.dumps({"request": rid, "route": path[:40], "status": code,
                          "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
    log.flush()


def make_server(svc: Service, port: int, log=sys.stdout):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code, body):
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
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= BODY_MAX
                                       else None)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def handle(svc: Service, method, path, headers, raw):
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle)


def env_file(path):
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env_file(sys.argv[1]) if len(sys.argv) > 1 else {}))
    one = [f"IVN_SECRET_{k.upper()}" for k in NOW] + ["IVN_SHOP_URL", "IVN_SHOP_KEY"]
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in one)):
        raise SystemExit("set " + ", ".join(one) + " (one shop), or IVN_LIBRARY_APP with a store (many shops)")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
