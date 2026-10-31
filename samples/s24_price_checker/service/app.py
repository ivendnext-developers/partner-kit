#!/usr/bin/env python3
"""S24 — *Price-checker kiosk*: the service that serves the kiosk's page and answers each scan (standard library only).

    GET  /                    the kiosk's page (its address carries #shop=<the shop's site>&kiosk=<code>)
    GET  /kiosk.js · /kiosk.css
    POST /prc/price           {"shop", "kiosk", "scan", "date"}  →  200 {"status": "found", "item", "price", ...}
                                                                   or {"status": "not_found" | "no_price" | ...}
    GET  /health              200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

A kiosk is a browser on a tablet: it holds no secret and signs nothing. Its call names its shop and its kiosk; the service
answers only for a shop that connected (or the one shop it is set up for) and a Kiosk record of that code which the shop
has switched on, read with the app's own integration key and kept one minute (``KIOSK_TTL``). Then it asks the shop:
its barcode lookup (``ivendnext_mpos.api.v1.scan_barcode``) and its line pricer
(``ivendnext_mpos.api.v1.get_item_details``), both whitelisted and read-only as called here (never a ``rate``).
The service writes nothing to the shop and keeps nothing but the Kiosk records it read.

ONE SHOP (env or an env file):
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_prc), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the key of the app's own user
                       ("user:<email>": "<api key>:<api secret>"); a kiosk's call names its shop in its body.
PRC_PREFIX (default PP PRC; IVENDNEXT PRC for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below).
"""

from __future__ import annotations

import collections
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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import price  # noqa: E402
import shops  # noqa: E402

KIOSK_TTL, READ_TIMEOUT, BODY_MAX = 60, 3.0, 2048
MISSES_PER_MINUTE = 20          # unknown kiosk codes read from one shop per minute, per copy of the service: a guesser
                                # cannot make the service hammer the shop. A code the shop has made (seen once) is never held
                                # back, so a guesser cannot lock a real kiosk out
SCAN_BARCODE = "/api/method/ivendnext_mpos.api.v1.scan_barcode"
PRICER = "/api/method/ivendnext_mpos.api.v1.get_item_details"
STATIC = {"/": ("kiosk.html", "text/html; charset=utf-8"), "/kiosk.js": ("kiosk.js", "text/javascript; charset=utf-8"),
          "/kiosk.css": ("kiosk.css", "text/css; charset=utf-8")}


class ShopUnreadable(Exception):
    pass


class NotPriced(Exception):
    """The shop refused to price the item (disabled, past its end of life, a template): its 4xx answer."""


class Busy(Exception):
    """Too many unknown kiosk codes from one shop this minute: the code is not looked up."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _call(url: str, key: str, path: str, body: dict | None = None, timeout: float = READ_TIMEOUT) -> dict:
    """One call to the shop with the app's key: GET (no body) or POST JSON. Its JSON, or HTTPError / ShopUnreadable."""
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Authorization": f"token {key}", "Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url.rstrip("/") + path, data=data, headers=headers)
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}") or {}
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError, http.client.HTTPException) as e:
        raise ShopUnreadable(type(e).__name__) from None


class ShopApi:
    """The three reads the service makes, each with the app's key. Swapped for a stand-in in the tests."""

    def kiosk(self, url: str, key: str, prefix: str, code: str) -> dict | None:
        """The Kiosk record; None when the shop says that record does not exist. Any other 404 (no such record type: a
        wrong prefix) or any other refusal is unreadable, never "no kiosk"."""
        path = "/api/resource/" + urllib.parse.quote(f"{prefix} Kiosk") + "/" + code
        try:
            return _call(url, key, path).get("data") or None
        except urllib.error.HTTPError as e:
            body = e.read() or b""
            e.close()
            if e.code == 404 and f"{prefix} Kiosk {code}".encode() in body:
                return None
            raise ShopUnreadable(f"the shop answered {e.code}") from None

    def scan(self, url: str, key: str, text: str) -> dict:
        """The shop's barcode lookup: a barcode, a serial number or a batch. {} when nothing matches."""
        try:
            return _call(url, key, SCAN_BARCODE, {"search_value": text}).get("message") or {}
        except urllib.error.HTTPError as e:
            e.close()
            if e.code == 417:       # the lookup's own refusal (a batch of an item that has serial numbers): no match
                return {}
            raise ShopUnreadable(f"the shop answered {e.code}") from None

    def price(self, url: str, key: str, args: dict) -> dict:
        """The shop's line pricer for one unit."""
        if "rate" in args:      # an explicit refusal, not an assert (python -O drops asserts)
            raise ValueError("never send a rate: the shop's pricer may then write a price row")
        try:
            return _call(url, key, PRICER, {"args": args}).get("message") or {}
        except urllib.error.HTTPError as e:
            e.close()
            if e.code == 417:       # the pricer refused the item (disabled, past its end of life, a template); any other
                raise NotPriced(str(e.code)) from None   # refusal (a 404: no such call on this shop) is unreadable
            raise ShopUnreadable(f"the shop answered {e.code}") from None


class Service:
    def __init__(self, conf: dict, store=None, api=None, clock=time.monotonic, today=None):
        self.prefix = (conf.get("PRC_PREFIX") or "PP PRC").strip()
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.api, self.clock = api or ShopApi(), clock
        self.today = today or (lambda: datetime.datetime.now(datetime.timezone.utc).date())
        self.cache, self.known, self.lock = {}, set(), threading.Lock()
        self.misses = collections.defaultdict(collections.deque)
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
            self.one = None
        else:                                           # one shop, from the settings
            self.one = {"url": conf["IVN_SHOP_URL"].rstrip("/"), "key": conf["IVN_SHOP_KEY"]}

    def shop(self, named) -> tuple[str, dict | None]:
        """(the shop's name for the cache, its address and the app's key there): None for a shop that did not connect,
        or one that has not handed over its integration user's key yet."""
        if self.one:
            return "-", self.one
        site = shops.site_of(named)
        record = self.store.get(site) if site else None
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        return site or "", ({"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None)

    def _missed(self, name: str) -> bool:
        """True when this shop has had MISSES_PER_MINUTE unknown codes in the last minute (then the shop is not read)."""
        now = self.clock()
        with self.lock:
            q = self.misses[name]
            while q and now - q[0] > 60:
                q.popleft()
            return len(q) >= MISSES_PER_MINUTE

    def kiosk(self, name: str, shop: dict, code: str) -> dict | None:
        """The shop's Kiosk record, as the pricer needs it, kept KIOSK_TTL seconds (so switching it off stops it within a
        minute). None: no such kiosk, or switched off. ``Busy`` when the shop has had too many unknown codes this minute and
        this code is not one the shop has made: a guesser's codes are not looked up, a real kiosk's always are."""
        now = self.clock()
        with self.lock:
            hit, known = self.cache.get((name, code)), (name, code) in self.known
        if hit and now - hit[0] < KIOSK_TTL:
            return hit[1]
        if not known and self._missed(name):
            raise Busy()
        record = self.api.kiosk(shop["url"], shop["key"], self.prefix, code)
        if record is None:
            with self.lock:
                self.misses[name].append(now)
            return None
        k = price.kiosk_of(record)
        with self.lock:
            self.cache[(name, code)] = (now, k)
            self.known.add((name, code))
        return k

    def price(self, raw: bytes) -> tuple[int, dict]:
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return 400, price.refusal("bad_request")
        code, text = price.kiosk_code(body.get("kiosk")), price.scan_text(body.get("scan"))
        if not code:
            return 403, price.refusal("not_set_up")
        if not text:
            return 400, price.refusal("bad_request")
        try:
            name, shop = self.shop(body.get("shop"))
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was read
            return 503, price.refusal("unavailable")
        if not shop:                    # the same words for a shop the app does not know: nothing to learn here
            return 403, price.refusal("not_set_up")
        try:
            kiosk = self.kiosk(name, shop, code)
            if not kiosk:
                return 403, price.refusal("not_set_up")
            hit = self.api.scan(shop["url"], shop["key"], text)
            if not isinstance(hit, dict) or not isinstance(hit.get("item_code"), str) or not hit["item_code"]:
                return 200, price.refusal("not_found")
            args = price.pricer_args(kiosk, hit, price.kiosk_date(body.get("date"), self.today()))
            answer = price.answer_of(self.api.price(shop["url"], shop["key"], args), kiosk)
        except Busy:
            return 429, price.refusal("busy")
        except NotPriced:
            return 200, price.refusal("not_on_sale")
        except ShopUnreadable:
            return 503, price.refusal("unavailable")
        if answer.get("image"):
            answer["image"] = shop["url"] + answer["image"]
        return 200, answer

    def csp(self) -> str:
        imgs = "https:" + (f" {self.one['url']}" if self.one and self.one["url"].startswith("http://") else "")
        return ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
                f"img-src {imgs}; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, bytes, dict]:
        """Every call: (status, body, headers). The web server and the function entry both use it."""
        path = path.split("?", 1)[0]
        if method == "GET" and path == "/health":
            return _json(200, {"status": "ok"})
        if method == "GET" and path in STATIC:
            fname, ctype = STATIC[path]
            with open(os.path.join(HERE, fname), "rb") as f:
                data = f.read()
            return 200, data, {"Content-Type": ctype, "Content-Security-Policy": self.csp(),
                               "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
                               "Cache-Control": "no-cache"}
        if method != "POST":
            return _json(404, {"error": "not found"})
        if raw is not None and len(raw) > BODY_MAX:
            return _json(413, {"error": "too large"})
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return _json(*shops.handle(self.store, self.app, path, headers, raw or b""))
        if path == "/prc/price":
            return _json(*self.price(raw or b""))
        return _json(404, {"error": "not found"})


def _json(code: int, body: dict) -> tuple[int, bytes, dict]:
    return code, json.dumps(body).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store",
                                             "X-Content-Type-Options": "nosniff"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
    """One call, and one log line (the route, the status and the time; never the body, the scan, a code or a key)."""
    t0 = time.monotonic()
    code, body, hdrs = svc.handle(method, path, headers, raw)
    print(json.dumps({"route": path.split("?", 1)[0][:20], "status": code, "ms": int((time.monotonic() - t0) * 1000)}),
          flush=True)
    return code, body, hdrs


def make_server(svc: Service, port: int):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _answer(self, method: str):
            raw = None
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n < 0 or n > BODY_MAX:
                    code, body, hdrs = _json(413, {"error": "too large"})
                    return self._send(code, body, hdrs)
                raw = self.rfile.read(n)
            self._send(*handle(svc, method, self.path, self.headers, raw))

        def _send(self, code: int, body: bytes, hdrs: dict):
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._answer("GET")

        def do_POST(self):
            self._answer("POST")

        def log_message(self, fmt, *args):     # the framework's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


_KEPT: dict = {}   # the function's settings, opened on the first call of each copy and kept while it lives


def lambda_handler(event, context=None):
    """As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b). The template's ``function``
    reads the load balancer's call; the answer carries its own content type, because this app also serves a page."""
    if "svc" not in _KEPT:
        _KEPT["svc"] = Service(dict(os.environ))
    method, path, headers, raw = function.request(event)
    code, body, hdrs = handle(_KEPT["svc"], method, path, headers, raw)
    return {"statusCode": code, "statusDescription": f"{code} {'OK' if code == 200 else 'Error'}",
            "isBase64Encoded": False, "headers": hdrs, "body": body.decode("utf-8")}


def env_file(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env_file(sys.argv[1]) if len(sys.argv) > 1 else {}))
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_SHOP_URL and IVN_SHOP_KEY (one shop), or IVN_LIBRARY_APP with a store (many shops)")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
