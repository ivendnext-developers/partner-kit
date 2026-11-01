#!/usr/bin/env python3
"""S37 — *Age-restricted sale check*: the service behind the shop's capture on scan and its check before payment
(standard library only).

    POST /age/scan    the shop's signed scan (``capture/1``)   →  200 {"verdict": "notice", "message": …, "sale_attributes": […]}
                      or {"verdict": "allow"} (no age, or this sale already asked about at that age or above)
    POST /age/check   the shop's signed check (``check/1``)    →  200 {"verdict": "allow" | "refuse", ...}
    GET  /health      200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

Each route is checked with ITS OWN secret, the one the install made for that service: ``<app>:sub:scan`` for the scan,
``<app>:sub:check`` for the check. A sale that sells nothing (a refund) is allowed at once, without reading the shop.
Otherwise the shop's settings (``<prefix> Settings``, the record ``Default``) and its item groups (with their
``<prefix>_min_age``) are read with the app's integration key and kept one minute (``KEPT_TTL``), and the items' own ages
are read for the codes not already kept (one call, kept one minute), then the templates of variants with no age of their
own (a variant does not inherit a field its template gained later). The service writes nothing to the shop.

When the shop cannot be read, refuses the key, or has not handed over its integration user's key yet, the service
answers 503 and the till applies each subscription's down answer (``allow_and_flag`` in this manifest: the item goes on,
or the sale is paid, and it is flagged on *Sales to review*).

ONE SHOP (env or an env file):
    IVN_SCAN_SECRET    the scan's secret (handed back at install as pp_age:sub:scan)
    IVN_CHECK_SECRET   the check's secret (pp_age:sub:check)
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_age), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the two secrets and its integration
                       user's key ("user:<email>": "<api key>:<api secret>"); every call names its shop (X-iVendNext-Site).
AGE_PREFIX (default PP AGE; IVENDNEXT AGE for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

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
import agecheck  # noqa: E402
import function  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

KEPT_TTL, READ_TIMEOUT = 60, 0.45    # three steps of reads at most (settings and groups; the items; their templates), each
                                     # 0.45 s per wait on its connection, inside the scan's 1.5 s; a slower shop gets the down answer
ITEMS_MAX = 20000                    # item ages kept per running copy; past it the copy forgets them all and reads again
#        route        (secret key, read the context)
ROUTES = {"/age/scan": ("scan", agecheck.scan_context),
          "/age/check": ("check", agecheck.check_context)}


class ShopUnreadable(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


class ShopApi:
    """The reads the service makes, with the shop's own key. Swapped for a stand-in in the tests."""

    def _get(self, url: str, key: str, path: str, query: dict | None = None, missing=False):
        q = f"?{urllib.parse.urlencode(query)}" if query else ""
        req = urllib.request.Request(f"{url.rstrip('/')}{path}{q}",
                                     headers={"Authorization": f"token {key}", "Accept": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=READ_TIMEOUT) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            e.close()
            if missing and e.code == 404:
                return None
            raise ShopUnreadable(f"the shop answered {e.code}") from None
        except (OSError, http.client.HTTPException, ValueError) as e:   # OSError: URLError, timeouts, TLS, a cut
            raise ShopUnreadable(type(e).__name__) from None             # connection; HTTPException: a cut answer

    @staticmethod
    def _data(out, kind):
        data = out.get("data") if isinstance(out, dict) else None
        if not isinstance(data, kind):
            raise ShopUnreadable("the shop's answer is not records")
        return data

    def settings(self, url: str, key: str, prefix: str):
        """The record ``Default`` of ``<prefix> Settings``, or ``None`` when the shop has not made it."""
        out = self._get(url, key, "/api/resource/" + urllib.parse.quote(f"{prefix} Settings") + "/Default", missing=True)
        return None if out is None else self._data(out, dict)

    def groups(self, url: str, key: str, prefix: str) -> list:
        """Every item group, with its place in the tree and the app's age."""
        p = prefix.lower().replace(" ", "_")
        return self._data(self._get(url, key, "/api/resource/Item%20Group", {
            "fields": json.dumps(["name", "lft", "rgt", f"{p}_min_age"]), "limit_page_length": 0}), list)

    def items(self, url: str, key: str, prefix: str, codes: list) -> list:
        """The named items' own ages, and the template each variant is made from."""
        p = prefix.lower().replace(" ", "_")
        return self._data(self._get(url, key, "/api/resource/Item", {
            "fields": json.dumps(["name", f"{p}_min_age", "variant_of"]), "filters": json.dumps([["name", "in", codes]]),
            "limit_page_length": 0}), list)


class Service:
    def __init__(self, conf: dict, store=None, api=None, clock=time.monotonic, now=time.time):
        self.prefix = (conf.get("AGE_PREFIX") or "PP AGE").strip()
        self.app = oneshop.value(conf, oneshop.MANY)
        self.api, self.clock, self.now, self.lock = api or ShopApi(), clock, now, threading.Lock()
        self.kept, self.item_ages, self.asked = {}, {}, agecheck.Asked(clock)
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            one = oneshop.settings(conf, ["IVN_SCAN_SECRET", "IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"])
            self.secrets = {"scan": one["IVN_SCAN_SECRET"], "check": one["IVN_CHECK_SECRET"]}
            self.shop = {"url": one["IVN_SHOP_URL"].rstrip("/"), "key": one["IVN_SHOP_KEY"]}

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

    def ages(self, name: str, shop: dict | None, codes: list) -> tuple[dict, dict, dict]:
        """(the shop's settings, its item groups, the named items' own ages and templates), each kept KEPT_TTL seconds for
        that shop and that key: one step for the settings and the groups, one for the items not already kept, and one for
        the templates of variants with no age of their own."""
        if not shop:
            raise ShopUnreadable("the shop has not handed over its integration user's key")
        url, key, now = shop["url"], shop["key"], self.clock()
        mine = (name, key)                              # an item's age is kept for this shop and this key only
        items = {}
        with self.lock:
            hit = self.kept.get(name)
        if not (hit and hit[1] == key and now - hit[0] < KEPT_TTL):
            with ThreadPoolExecutor(max_workers=2) as pool:
                s = pool.submit(self.api.settings, url, key, self.prefix)
                g = pool.submit(self.api.groups, url, key, self.prefix)
                hit = (now, key, (agecheck.settings_of(s.result()), agecheck.groups_of(g.result(), self.prefix)))
            with self.lock:
                self.kept[name] = hit
        for _step in range(2):                          # the items, then the templates of those with no age of their own
            with self.lock:
                items.update({c: v[1] for c in codes if (v := self.item_ages.get((*mine, c))) and now - v[0] < KEPT_TTL})
            missing = sorted(set(codes) - set(items))
            if missing:
                read = agecheck.items_of(self.api.items(url, key, self.prefix, missing), self.prefix)
                if set(missing) - set(read):
                    raise ShopUnreadable("an item could not be read")
                with self.lock:
                    if len(self.item_ages) >= ITEMS_MAX:
                        self.item_ages.clear()
                    self.item_ages.update({(*mine, c): (now, read[c]) for c in missing})
                items.update(read)
            codes = sorted({t for age, t in items.values() if t and not age})
        return hit[2][0], hit[2][1], items

    def scan(self, name: str, shop: dict | None, ctx: dict) -> dict:
        line, ref = ctx["line"], ctx.get("sale_ref") or ""
        settings, groups, items = self.ages(name, shop, [line["item_code"]])
        age = agecheck.age_of(line["item_code"], line.get("item_group") or "", items, groups)
        if not age or self.asked.covered(name, ref, age):
            return {"verdict": "allow"}
        self.asked.remember(name, ref, age)
        return agecheck.on_scan(ctx, age, settings, agecheck.today_at(settings["hours"], self.now()), self.prefix)

    def check(self, name: str, shop: dict | None, ctx: dict) -> dict:
        if not agecheck.sells(ctx):
            return {"verdict": "allow"}                 # a refund: nothing leaves the shop, nothing to read
        _settings, groups, items = self.ages(name, shop, sorted({x["item_code"] for x in ctx["lines"]}))
        ages = [agecheck.age_of(x["item_code"], x["item_group"], items, groups) for x in ctx["lines"]]
        return agecheck.on_check(ctx, ages, agecheck.checked_age(ctx, self.prefix))

    def answer(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if path not in ROUTES:
            return 404, {"error": "not found"}
        route_key, read = ROUTES[path]
        try:
            name, secrets, shop = self.caller(route_key, headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(agecheck.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(route_key)
        try:
            ctx = read(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        try:
            return 200, (self.scan if route_key == "scan" else self.check)(name, shop, ctx)
        except (ShopUnreadable, ValueError) as e:       # the shop did not answer, or not with records: nothing was judged
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "the shop cannot be read"}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > agecheck.BODY_MAX:
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
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= agecheck.BODY_MAX else None)
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
    if not (oneshop.many(conf) or all(oneshop.value(conf, k) for k in ("IVN_SCAN_SECRET", "IVN_CHECK_SECRET",
                                                                       "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_SCAN_SECRET, IVN_CHECK_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), "
                         "or IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
