#!/usr/bin/env python3
"""S23 — *Till guard rules*: the service behind the shop's check before payment and its capture on scan (standard
library only).

    POST /tgr/check   the shop's signed check (``check/1``)   →  200 {"verdict": "allow" | "refuse" | "approve" | "ask", ...}
    POST /tgr/scan    the shop's signed scan (``capture/1``)  →  200 {"verdict": "confirm", "question": ...}, or, with the
                      shop's *Warn of a shorter-dated batch* on, {"verdict": "notice" | "allow", ...}
    GET  /health      200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

Each route is checked with ITS OWN secret, the one the install made for that service: ``<app>:sub:guard`` for the check,
``<app>:sub:on_scan`` for the scan. The rules are the shop's own: its settings record ``<prefix> Settings`` / ``Default``,
read with the app's integration key and kept one minute (``SETTINGS_TTL``). When the shop cannot be read, the last
rules read are used for up to ten minutes (``SETTINGS_STALE``); after that the service answers 503 and the till applies
the subscription's down answer (``allow_and_flag`` in this manifest: the sale goes on and is flagged). No record yet =
every rule off. The service writes nothing to the shop.

*Warn of a shorter-dated batch* reads the shop at each scan: one call to ``ivendnext_mpos.api.v1.get_batch_qty`` for the
store's batches of the item with stock, and each batch's expiry date from its Batch record, kept a day (a batch's expiry
does not change). The answer aims at SCAN_BUDGET (1 s, inside the scan's 1.5 s): each read is given only the time left, a
read is not started once it has run out, and then the answer is a plain allow — a warning missed, never a late one. Bound:
a timeout limits each step of a read (the connection, each piece of the answer), not the read as a whole, so a shop that
answers a byte at a time can hold one read past it; past 1.5 s the till applies the down answer (the item goes on, flagged).

ONE SHOP (env or an env file):
    IVN_CHECK_SECRET   the check's secret (handed back at install as pp_tgr:sub:guard)
    IVN_SCAN_SECRET    the scan's secret (pp_tgr:sub:on_scan)
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_tgr), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the two secrets and its integration
                       user's key ("user:<email>": "<api key>:<api secret>"); every call names its shop (X-iVendNext-Site).
TGR_PREFIX (default PP TGR; IVENDNEXT TGR for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

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
import function  # noqa: E402
import guard  # noqa: E402
import shops  # noqa: E402

SETTINGS_TTL, SETTINGS_STALE, READ_TIMEOUT = 60, 600, 1.0   # each step of the read inside the scan's 1.5 s (per step, not a wall clock)
SCAN_BUDGET, EXPIRY_TTL, EXPIRY_MAX = 1.0, 86400, 5000       # the shelf-life answer's whole time; a batch's expiry, kept a day
#        route          (secret key, read the context,     answer)
ROUTES = {"/tgr/check": ("guard", guard.check_context, guard.on_check),
          "/tgr/scan": ("on_scan", guard.scan_context, guard.on_scan)}


class ShopUnreadable(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def read_settings(url: str, key: str, prefix: str, timeout: float = READ_TIMEOUT) -> dict | None:
    """The shop's ``<prefix> Settings`` record ``Default`` over the record API; ``None`` when the shop says that record does
    not exist yet. Any other 404 (no such record type: a wrong prefix; a wrong address) is unreadable, never "rules off"."""
    path = "/api/resource/" + urllib.parse.quote(f"{prefix} Settings") + "/Default"
    req = urllib.request.Request(url.rstrip("/") + path, headers={"Authorization": f"token {key}", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return (json.loads(r.read() or b"{}") or {}).get("data") or None
    except urllib.error.HTTPError as e:
        body = e.read() or b""
        e.close()
        if e.code == 404 and f"{prefix} Settings Default".encode() in body:
            return None
        raise ShopUnreadable(f"the shop answered {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        raise ShopUnreadable(type(e).__name__) from None


def _get(url: str, key: str, path: str, timeout: float):
    req = urllib.request.Request(url.rstrip("/") + path, headers={"Authorization": f"token {key}", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}") or {}
    except urllib.error.HTTPError as e:
        e.close()
        raise ShopUnreadable(f"the shop answered {e.code}") from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        raise ShopUnreadable(type(e).__name__) from None


def read_batches(url: str, key: str, item: str, store: str, timeout: float) -> list[tuple[str, float]]:
    """The store's batches of the item with stock, as the shop computes them: ``[(batch, quantity)]``. The integration
    user needs read on Batch (the shop gives it in Role Permissions: a manifest grants rights on its own record types only)."""
    q = urllib.parse.urlencode({"item_code": item, "warehouse": store})
    rows = _get(url, key, "/api/method/ivendnext_mpos.api.v1.get_batch_qty?" + q, timeout).get("message") or []
    return [(str(r.get("batch_no")), float(r.get("qty") or 0)) for r in rows if isinstance(r, dict) and r.get("batch_no")]


def read_expiry(url: str, key: str, batch: str, timeout: float) -> str:
    """A batch's expiry date (``YYYY-MM-DD``), or ``""`` when it has none."""
    data = _get(url, key, "/api/resource/Batch/" + urllib.parse.quote(batch, safe=""), timeout).get("data") or {}
    return str(data.get("expiry_date") or "")[:10]


class Service:
    def __init__(self, conf: dict, store=None, reader=read_settings, clock=time.monotonic,
                 batches=read_batches, expiry=read_expiry):
        self.prefix = (conf.get("TGR_PREFIX") or "PP TGR").strip()
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.reader, self.clock, self.cache, self.lock = reader, clock, {}, threading.Lock()
        self.batches, self.expiry, self.expiries = batches, expiry, {}
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secrets = {"guard": conf["IVN_CHECK_SECRET"], "on_scan": conf["IVN_SCAN_SECRET"]}
            self.shop = {"url": conf["IVN_SHOP_URL"], "key": conf["IVN_SHOP_KEY"]}

    def caller(self, route_key: str, headers) -> tuple[str, list[str], dict | None]:
        """(the shop's name for the cache, the secrets this route's call may be signed with, the shop's address and key)."""
        if not self.app:
            return "-", [self.secrets[route_key]], self.shop
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{route_key}")]
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        shop = {"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None
        return site or "", secrets, shop

    def rules(self, name: str, shop: dict | None) -> dict:
        """The shop's rules, kept SETTINGS_TTL seconds; the last ones read stand in for SETTINGS_STALE if the shop is down."""
        now = self.clock()
        with self.lock:
            hit = self.cache.get(name)
        if hit and now - hit[0] < SETTINGS_TTL:
            return hit[1]
        try:
            if not shop:
                raise ShopUnreadable("the shop has not handed over its integration user's key")
            rules = guard.settings_of(self.reader(shop["url"], shop["key"], self.prefix))
        except ShopUnreadable:
            if hit and now - hit[0] < SETTINGS_STALE:
                return hit[1]
            raise
        with self.lock:
            self.cache[name] = (now, rules)
        return rules

    def shelf(self, name: str, shop: dict, ctx: dict, t0: float) -> dict:
        """*Warn of a shorter-dated batch*: read the store's batches and their expiry dates inside SCAN_BUDGET, counted
        from ``t0``; when the shop cannot be read in time the answer is allow (the item goes on, nothing is shown)."""
        def left():
            return SCAN_BUDGET - (self.clock() - t0)
        try:
            if left() <= 0:
                return {"verdict": "allow"}
            line = ctx["line"]
            stock = self.batches(shop["url"], shop["key"], line["item_code"], ctx.get("store") or "", left())
            dated = []
            for batch, qty in stock:
                if qty <= 0:
                    continue
                hit = self.expiries.get((name, batch))
                if not hit or self.clock() - hit[0] >= EXPIRY_TTL:
                    if left() <= 0:
                        return {"verdict": "allow"}
                    hit = (self.clock(), self.expiry(shop["url"], shop["key"], batch, left()))
                    with self.lock:
                        if len(self.expiries) >= EXPIRY_MAX:
                            self.expiries.clear()
                        self.expiries[(name, batch)] = hit
                if hit[1]:
                    dated.append((hit[1], batch))
            if left() <= 0:                         # the answer would come too late to show: never a late warning
                return {"verdict": "allow"}
            return guard.on_scan_shelf(ctx, dated)
        except Exception:                           # any failure of the read (an answer of the wrong shape included): a plain allow
            return {"verdict": "allow"}

    def answer(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        t0 = self.clock()
        if path not in ROUTES:
            return 404, {"error": "not found"}
        route_key, read, decide = ROUTES[path]
        try:
            name, secrets, shop = self.caller(route_key, headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(guard.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            ctx = read(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if path == "/tgr/check" and ctx["stage"] != "sale" and not guard.sold_lines(ctx):
            return 200, {"verdict": "allow"}            # a plain return sells nothing: no need to read the shop
        try:
            rules = self.rules(name, shop)
        except ShopUnreadable:
            return 503, {"error": "the shop's settings cannot be read"}
        if path == "/tgr/scan" and rules["shelf_warning"]:
            return 200, self.shelf(name, shop, ctx, t0)
        return 200, decide(ctx, rules)

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > guard.BODY_MAX:
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
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= guard.BODY_MAX else None)
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
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_CHECK_SECRET", "IVN_SCAN_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_CHECK_SECRET, IVN_SCAN_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), "
                         "or IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
