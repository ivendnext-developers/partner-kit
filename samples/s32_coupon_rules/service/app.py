#!/usr/bin/env python3
"""S32 — *Coupon rules*: the service behind the shop's check before payment (standard library only).

    POST /cpn/check   the shop's signed check (``check/1``)   →  200 {"verdict": "allow" | "refuse", ...}
    GET  /health      200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

The call is checked with the secret the install made for the check, ``<app>:sub:coupons``. A sale with no coupon is
allowed at once, without reading the shop. Otherwise the shop's switched-on rule records (``<prefix> Rule``, every one) are
read with the app's integration key and kept one minute (``RULES_TTL``); a first-purchase rule then counts the customer's
submitted sales in the shop, live, through the shop's own ``ivendnext_mpos.api.v1.get_count`` (POS Invoices and Sales
Invoices made outside the till, both at once; neither a return). The service writes nothing to the shop.

When the shop cannot be read, or has not handed over its integration user's key yet, the service answers 503 and the till
applies the subscription's down answer (``allow_and_flag`` in this manifest: the sale goes on and is flagged). When the
shop refuses the key (401 or 403: a key withdrawn, a user disabled, a right not given), a sale carrying any coupon is
refused in words that say so: a coupon the shop restricted is never given unchecked because of a refused key. Any other
error answer (a 404, a 500) is treated as the shop being down: 503, the down answer applies.

ONE SHOP (env or an env file):
    IVN_CHECK_SECRET   the check's secret (handed back at install as pp_cpn:sub:coupons)
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_cpn), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the check's secret and its integration
                       user's key ("user:<email>": "<api key>:<api secret>"); every call names its shop (X-iVendNext-Site).
CPN_PREFIX (default PP CPN; IVENDNEXT CPN for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

import http.client
import json
from concurrent.futures import ThreadPoolExecutor
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
import coupons  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

KEY, ROUTE = "coupons", "/cpn/check"   # the subscription's key in the manifest; its secret is "<app>:sub:<key>"
RULES_TTL, READ_TIMEOUT = 60, 0.9      # two steps at most (the rules, then both counts at once) inside the check's 3 s
GET_COUNT = "/api/method/ivendnext_mpos.api.v1.get_count"
KEY_REFUSED = "Coupon rules cannot read your shop: it refused the app's user. Remove the coupon, or ask your administrator to check the app's setup."
# what counts as having bought before: a submitted sale that is not a return, at the till or in the back office
# (a consolidated Sales Invoice is the till's sales a second time, so it is left out, as the till's own customer history does)
SALES = (("POS Invoice", [["docstatus", "=", 1], ["is_return", "=", 0]]),
         ("Sales Invoice", [["docstatus", "=", 1], ["is_return", "=", 0], ["is_consolidated", "=", 0]]))


class ShopUnreadable(Exception):
    pass


class KeyRefused(ShopUnreadable):
    """The shop answered 401 or 403 to the app's user key: a key withdrawn, a user disabled or a right not given (the
    first-purchase rule reads POS Invoice and Sales Invoice), not an outage."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


class ShopApi:
    """The reads the service makes, with the shop's own key. Swapped for a stand-in in the tests."""

    def _get(self, url: str, key: str, path: str, query: dict):
        req = urllib.request.Request(f"{url.rstrip('/')}{path}?{urllib.parse.urlencode(query)}",
                                     headers={"Authorization": f"token {key}", "Accept": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=READ_TIMEOUT) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            e.close()
            raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)(f"the shop answered {e.code}") from None
        except (OSError, http.client.HTTPException, ValueError) as e:   # OSError: URLError, timeouts, TLS, a cut
            raise ShopUnreadable(type(e).__name__) from None             # connection; HTTPException: a cut answer

    def rules(self, url: str, key: str, prefix: str) -> list:
        """The shop's switched-on Rule records (every one: ``limit_page_length`` 0), each with all its fields: a retailer
        still on 1.0.1 has no *Sale needed for each use*, and a read naming that field would fail for it."""
        out = self._get(url, key, "/api/resource/" + urllib.parse.quote(prefix + " Rule"),
                        {"fields": json.dumps(["*"]), "filters": json.dumps([["enabled", "=", 1]]),
                         "limit_page_length": 0})
        return out.get("data") if isinstance(out, dict) else None

    def count(self, url: str, key: str, doctype: str, filters: list) -> int:
        """How many records match, by the shop's permission-checked count. Anything but a whole number is unreadable."""
        out = self._get(url, key, GET_COUNT, {"doctype": doctype, "filters": json.dumps(filters)})
        n = out.get("message") if isinstance(out, dict) else None
        if not isinstance(n, int) or isinstance(n, bool) or n < 0:
            raise ShopUnreadable("the count is not a whole number")
        return n


class Service:
    def __init__(self, conf: dict, store=None, api=None, clock=time.monotonic):
        self.prefix = (conf.get("CPN_PREFIX") or "PP CPN").strip()
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.api, self.clock, self.kept, self.lock = api or ShopApi(), clock, {}, threading.Lock()
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secret = conf["IVN_CHECK_SECRET"]
            self.shop = {"url": conf["IVN_SHOP_URL"].rstrip("/"), "key": conf["IVN_SHOP_KEY"]}

    def caller(self, headers) -> tuple[str, list[str], dict | None]:
        """(the shop's name for the cache, the secrets this call may be signed with, the shop's address and key)."""
        if not self.app:
            return "-", [self.secret], self.shop
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{KEY}")]
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        shop = {"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None
        return site or "", secrets, shop

    def rules(self, name: str, shop: dict | None) -> dict:
        """The shop's rules, kept RULES_TTL seconds for that shop and that key."""
        if not shop:
            raise ShopUnreadable("the shop has not handed over its integration user's key")
        now = self.clock()
        with self.lock:
            hit = self.kept.get(name)
        if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:
            return hit[2]
        rules = coupons.rules_of(self.api.rules(shop["url"], shop["key"], self.prefix))
        with self.lock:
            self.kept[name] = (now, shop["key"], rules)
        return rules

    def prior_sales(self, shop: dict):
        """``customer → how many sales``, live: the till's and the back office's, counted at the same time (each read has
        its own timeout, so two in a row could outrun the check's 3 s). An error is raised in the ledgers' order: the
        till's first, so a till read that times out answers 503 even when the back office refused the key."""
        def count(customer: str) -> int:
            with ThreadPoolExecutor(max_workers=len(SALES)) as pool:
                return sum(pool.map(lambda s: self.api.count(shop["url"], shop["key"], s[0], [["customer", "=", customer]] + s[1]),
                                    SALES))
        return count

    def answer(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if path != ROUTE:
            return 404, {"error": "not found"}
        try:
            name, secrets, shop = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(coupons.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            ctx = coupons.check_context(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if not ctx["coupon_codes"]:
            return 200, {"verdict": "allow"}            # no coupon: nothing to judge, nothing to read
        try:
            rules = self.rules(name, shop)
            return 200, coupons.on_check(ctx, rules, self.prior_sales(shop))
        except KeyRefused:
            return 200, {"verdict": "refuse", "reason": KEY_REFUSED}
        except (ShopUnreadable, ValueError) as e:       # the shop did not answer, or not with records: nothing was judged
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "the shop cannot be read"}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > coupons.BODY_MAX:
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
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= coupons.BODY_MAX else None)
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
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_CHECK_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), "
                         "or IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
