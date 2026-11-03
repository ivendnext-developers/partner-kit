#!/usr/bin/env python3
"""S1 — warranty terms on CitiXsys hosting, for many retailers (standard library only).

    POST /point/warranty      the till key's call (signed by the shop)   →  200 {"message": {...}}
    the schedule ``pass``     every few minutes: each site's booked sales since the last pass get their warranties
    GET  /health              200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

It runs as a FUNCTION (app.json "runs": "function", "schedule"; ``lambda_handler`` below). The terms are the retailer's own
(``PP WRC Warranty Term``). A pass does what ``app.py`` does on your own server from a webhook (``register.py``): one warranty
per covered serial number and one Comment on the sale. The Comment is the record: the shops store (the table on hosting) keeps
only each site's place, one row per record type, because every pass reads that table's list of sites. A site's first pass
marks the site's own newest sale: older sales are left alone, also when one is saved again later.

When the app has no user's key yet, the shop refuses that key, or the shop cannot be read in time, the cashier is told so
in words (200, a warning message), never a guess. A pass that cannot read a site says so in the log and tries again next time.

MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 1a):
    IVN_LIBRARY_APP    the app's id in the App library, with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE. Each shop
                       connects itself after its install and hands over the till key's secret and the key of the app's own
                       user ("user:<email>"); every call names its shop (X-iVendNext-Site).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path[:0] = [SAMPLE, HERE]
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import core  # noqa: E402  (the sample's pure core, unchanged)
import function  # noqa: E402
import oneshop  # noqa: E402
import register  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402
from tenant import Tenant, TenantError  # noqa: E402  (the sample's only door into iVendNext)

ROUTE, KEY = "/point/warranty", "warranty"     # the manifest's remote_keys[].key; its secret is "<app>:<key>"
TERM = "PP WRC Warranty Term"
BODY_MAX, SKEW_S, READ_S, TERMS_MAX = 64 * 1024, 300, 1.2, 1000     # two reads, inside the till's 3 seconds
PASS_READ_S, MARGIN_S = 8, 30       # a pass reads with more patience, and stops in time for the function's limit
OVERLAP_S, HANDLED_MAX = 600, 50000  # tills commit out of order; what this copy has handled, so the overlap costs little
EARLIEST = "2000-01-01 00:00:00"
TITLE = "Warranty"
NOT_SET_UP = ("Warranty terms is not set up yet: no key from this site has reached it. Ask your manager to press Connect "
              "again on the app.")
CANNOT_READ = "The warranty terms cannot be read right now. Try again in a moment."
NO_RIGHTS = "The app's user may not read items. Ask your manager to give its role read on Item."


def verified(secrets: list[bytes], headers, raw: bytes) -> bool:
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:
        return False
    return any(hmac.compare_digest(base64.b64encode(hmac.new(s, ts.encode() + b"." + raw, hashlib.sha256).digest()),
                                   sig.encode()) for s in secrets)


def terms_of(rows: list[dict]) -> dict:
    """The retailer's term rows, in the shape ``core`` reads."""
    out = {"items": {}, "groups": {}}
    for r in rows:
        if r.get("applies_to") == "Item" and r.get("item"):
            out["items"][r["item"]] = r.get("months")
        elif r.get("applies_to") == "Item Group" and r.get("item_group"):
            out["groups"][r["item_group"]] = r.get("months")
    return out


class SiteStore:
    """What ``register`` keeps for one site. In the shops store, each record type's place alone (never taken for a shop: its
    names hold ``CLAIM_MARK``). What was handled is on the sale, as its Comment (``has_our_comment``), and this copy of the
    function remembers it, to read less."""

    def __init__(self, store, site: str, terms: dict, handled: set):
        self.store, self.site, self._terms, self.handled, self.lock = store, site, terms, handled, threading.Lock()

    def _name(self, kind: str, *rest: str) -> str:
        return shops.CLAIM_MARK.join(("wrc", self.site, kind, *rest))

    def terms(self) -> dict:
        return dict(self._terms)

    def is_processed(self, doctype: str, name: str) -> bool:
        return (self.site, doctype, name) in self.handled

    def record(self, doctype: str, name: str, regs: list, comment, via: str) -> int:
        if len(self.handled) >= HANDLED_MAX:
            self.handled.clear()
        self.handled.add((self.site, doctype, name))
        return len(regs)

    def mark(self, doctype: str) -> dict | None:
        return self.store.get(self._name("mark", doctype))

    def start(self, doctype: str, newest: str) -> None:
        """The first pass: this site's place starts just after its own newest sale, on its own clock."""
        at = (datetime.fromisoformat(newest[:19]) + timedelta(seconds=1)).strftime("%Y-%m-%d %H:%M:%S")
        self.store.put(self._name("mark", doctype), {"at": at, "first": at, "from": at[:10]})

    def floor(self, doctype: str) -> tuple:
        m = self.mark(doctype) or {}
        return m.get("first"), m.get("from")

    def watermark(self, doctype: str, default: str) -> str:
        return (self.mark(doctype) or {}).get("at") or default

    def set_watermark(self, doctype: str, at: str) -> None:
        self.store.put(self._name("mark", doctype), {**(self.mark(doctype) or {}), "at": at})

    def event(self, kind: str, what: str) -> None:
        print(json.dumps({"site": self.site, "event": kind, "what": what[:300]}), flush=True)


def _warning(body: str) -> dict:
    return {"message": {"title": TITLE, "body": body, "level": "warning"}}


class Service:
    def __init__(self, conf: dict, store=None, tenant_of=None):
        self.app = oneshop.value(conf, oneshop.MANY)
        if not self.app:
            raise SystemExit("this form is for many shops: set IVN_LIBRARY_APP. For one shop run service/app.py")
        self.store = store or shops.open_store(conf)
        self.tenant_of = tenant_of or (lambda url, key, secret, timeout=READ_S: Tenant(url, key, secret, timeout=timeout))
        self.handled: set = set()

    def tenant(self, record: dict, timeout: float = READ_S):
        users = sorted(k for k in (record.get("secrets") or {}) if k.startswith("user:"))
        key, _, secret = (record["secrets"][users[0]] if users else "").partition(":")
        return self.tenant_of(record["url"], key, secret, timeout) if key and secret else None

    def one_pass(self, site: str, time_left) -> dict:
        """One site's booked sales since its last pass. A site that cannot be read keeps its place for the next pass."""
        record = self.store.get(site)
        door = self.tenant(record, PASS_READ_S) if record else None
        if not door:
            return {"site": site, "skipped": "no user's key yet"}
        try:
            rows = door.list(TERM, ["applies_to", "item", "item_group", "months"], [], "modified asc", TERMS_MAX)
            kept = SiteStore(self.store, site, terms_of(rows), self.handled)
            for dt in register.DOCTYPES:
                if not kept.mark(dt):
                    newest = door.list(dt, ["modified"], [["docstatus", "=", 1]], "modified desc", 1)
                    kept.start(dt, newest[0]["modified"] if newest else EARLIEST)
            return register.reconcile(kept, door, EARLIEST, time_left, OVERLAP_S, kept.floor)
        except TenantError as e:
            print(json.dumps({"site": site, "pass": "could not read", "why": str(e)[:200]}), flush=True)
            return {"site": site, "skipped": "could not read"}

    def answer(self, headers, raw: bytes) -> tuple[int, dict]:
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, f"{self.app}:{KEY}")
        if not secrets or not verified(secrets, headers, raw):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(KEY)
        try:
            context = json.loads(raw)["context"]
            if not isinstance(context, dict):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return 400, {"error": "bad request"}
        codes = sorted({line["item_code"] for line in context.get("lines") or []
                        if isinstance(line, dict) and line.get("item_code")})
        door = self.tenant(record)
        if not door:
            return 200, _warning(NOT_SET_UP)
        try:
            rows = door.list(TERM, ["applies_to", "item", "item_group", "months"], [], "modified asc", TERMS_MAX)
            terms = terms_of(rows)
            rest = [c for c in codes if c not in terms["items"]]    # an item's own term needs no group, and no right on Item
            terms["item_group"] = door.item_groups(rest) if rest else {}
        except TenantError as e:
            return 200, _warning(NO_RIGHTS if "403" in str(e) else CANNOT_READ)
        return 200, core.warranty_answer(context, terms)

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > BODY_MAX:
            return 413, {"error": "too large"}
        if path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.answer(headers, raw) if path == ROUTE else (404, {"error": "not found"})


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line (never the body, the context, a secret or a signature)."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    print(json.dumps({"request": (headers.get("X-iVendNext-Request-Id") or "-")[:40], "route": path[:40], "status": code,
                      "ms": int((time.monotonic() - t0) * 1000)}), flush=True)
    return code, out


def scheduled(svc: Service, name: str, seconds: float = 900) -> dict:
    """One scheduled pass: the sites this call claims, each freed as it finishes (``function.Claimed``)."""
    end = time.monotonic() + seconds - MARGIN_S
    store, out = function.Claimed(svc.store, seconds, kind="wrc"), {}     # a claim of its own: a feed reader works beside it
    for site in store.sites():
        try:
            if end - time.monotonic() > 0:
                out[site] = svc.one_pass(site, lambda: end - time.monotonic())
        except Exception as e:  # noqa: BLE001 — one site down never stops the others; it keeps its place
            print(json.dumps({"site": site, "pass": "stopped", "why": type(e).__name__}), flush=True)
            out[site] = {"site": site, "skipped": "stopped"}
        finally:
            store.release(site)
    return out


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 1a): settings from the environment.
lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle, scheduled)
