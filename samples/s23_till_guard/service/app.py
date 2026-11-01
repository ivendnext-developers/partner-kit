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

*Lowest prices* (the settings record names one of the retailer's price lists) reads the shop at a check that sells a
priced line and is not refused: that list's Item Price rows of the basket's items in the sale's currency that name no
customer, supplier or batch, about ``PRICE_CHUNK`` bytes of item codes a call, none started once less than ``READ_LEAST`` is left of
``CHECK_BUDGET`` (counted from the call's arrival, the settings read included, inside the check's 3 s); each
item's rows kept one minute and standing in for ten while the shop cannot be read, as the settings are. After that a large
sale is still sent to its approval, saying its lowest prices could not be checked; any other sale gets 503, and the till
applies the down answer. The refusals are worked out first, so a price list that cannot be read never stops one. The integration user
needs read on Item Price (given in Role Permissions, as for Batch).

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
import guard  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

SETTINGS_TTL, SETTINGS_STALE, READ_TIMEOUT = 60, 600, 1.0   # each step of the read inside the scan's 1.5 s (per step, not a wall clock)
SCAN_BUDGET, EXPIRY_TTL, EXPIRY_MAX = 1.0, 86400, 5000       # the shelf-life answer's whole time; a batch's expiry, kept a day
PRICE_FIELDS = ["item_code", "uom", "price_list_rate", "currency", "valid_from", "valid_upto"]
PRICE_CHUNK = 2000                            # the item codes' bytes per read, as sent (a request line stays under 4 KB)
CHECK_BUDGET, READ_LEAST = 2.0, 0.2           # a check's own time, from its arrival, inside the till's 3 s; the least a read is given
#        route          (secret key, read the context,     answer)
ROUTES = {"/tgr/check": ("guard", guard.check_context, guard.on_check),
          "/tgr/scan": ("on_scan", guard.scan_context, guard.on_scan)}


class ShopUnreadable(Exception):
    pass


READ_ERRORS = (urllib.error.URLError, OSError, http.client.HTTPException, ValueError)   # a cut answer or TLS too


def _object(raw: bytes) -> dict:
    """The answer's JSON object; anything else (a list, a proxy's page) is unreadable, never a crash."""
    data = json.loads(raw)                      # an empty body is not an answer either
    if not isinstance(data, dict):
        raise ValueError("the answer is not an object")
    return data


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
            data = _object(r.read()).get("data")
            if not isinstance(data, dict) or not data:
                raise ValueError("the answer carries no record")    # a missing record is the 404 above, never a 200
            return data
    except urllib.error.HTTPError as e:
        body = e.read() or b""
        e.close()
        if e.code == 404 and f"{prefix} Settings Default".encode() in body:
            return None
        raise ShopUnreadable(f"the shop answered {e.code}") from None
    except READ_ERRORS as e:
        raise ShopUnreadable(type(e).__name__) from None


def _get(url: str, key: str, path: str, timeout: float):
    req = urllib.request.Request(url.rstrip("/") + path, headers={"Authorization": f"token {key}", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            return _object(r.read())
    except urllib.error.HTTPError as e:
        e.close()
        raise ShopUnreadable(f"the shop answered {e.code}") from None
    except READ_ERRORS as e:
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


def read_lowest(url: str, key: str, price_list: str, items: list[str], currency: str,
                timeout: float = READ_TIMEOUT) -> list[dict]:
    """The retailer's Item Price rows of its *Lowest prices* list for these items, in the sale's currency, naming no customer,
    supplier or batch (``guard.lowest_prices`` picks from them, and would skip such a row if one came)."""
    q = urllib.parse.urlencode({"fields": json.dumps(PRICE_FIELDS), "limit_page_length": 0, "filters": json.dumps(
        [["price_list", "=", price_list], ["item_code", "in", items], ["currency", "=", currency],
         ["customer", "is", "not set"], ["supplier", "is", "not set"], ["batch_no", "is", "not set"]])})
    rows = _get(url, key, "/api/resource/" + urllib.parse.quote("Item Price") + "?" + q, timeout).get("data")
    if not isinstance(rows, list):
        raise ShopUnreadable("the shop's prices are not a list")
    return [r for r in rows if isinstance(r, dict)]


def utc_today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def _chunks(items: list[str]):
    """The items in reads whose codes, as ``read_lowest``'s query string carries them, stay within PRICE_CHUNK bytes."""
    chunk, size = [], 0
    for it in items:
        n = len(urllib.parse.quote_plus(json.dumps(it))) + 4          # the code and its ", " as urlencode sends them
        if chunk and size + n > PRICE_CHUNK:
            yield chunk
            chunk, size = [], 0
        chunk.append(it)
        size += n
    if chunk:
        yield chunk


class Service:
    def __init__(self, conf: dict, store=None, reader=read_settings, clock=time.monotonic,
                 batches=read_batches, expiry=read_expiry, prices=read_lowest, today=utc_today):
        self.prefix = (conf.get("TGR_PREFIX") or "PP TGR").strip()
        self.app = oneshop.value(conf, oneshop.MANY)
        self.reader, self.clock, self.cache, self.lock = reader, clock, {}, threading.Lock()
        self.batches, self.expiry, self.expiries = batches, expiry, {}
        self.prices, self.today, self.lowest_cache = prices, today, {}
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            one = oneshop.settings(conf, ["IVN_CHECK_SECRET", "IVN_SCAN_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"])
            self.secrets = {"guard": one["IVN_CHECK_SECRET"], "on_scan": one["IVN_SCAN_SECRET"]}
            self.shop = {"url": one["IVN_SHOP_URL"], "key": one["IVN_SHOP_KEY"]}

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

    def lowest(self, name: str, shop: dict | None, ctx: dict, rules: dict, t0: float) -> dict:
        """*Lowest prices*: ``{(item, unit): price}`` for the basket's priced sold items, read in chunks (``_chunks``) for the
        items not read in the last SETTINGS_TTL; an item's last rows stand in for SETTINGS_STALE while the shop cannot be read."""
        plist = rules["lowest_list"]
        items = sorted({ln["item_code"] for ln in guard.sold_lines(ctx) if ln["rate_minor"] > 0 and ln.get("item_code")})
        if not plist or not items:
            return {}
        now, rows, missing, mine_key = self.clock(), [], [], (name, plist)      # per shop: two shops may name one list
        with self.lock:
            hits = {it: self.lowest_cache.get(mine_key + (it,)) for it in items}
        for it in items:
            if hits[it] and now - hits[it][0] < SETTINGS_TTL:
                rows += hits[it][1]
            else:
                missing.append(it)
        if missing:
            todo = list(missing)
            try:
                if not shop:
                    raise ShopUnreadable("the shop has not handed over its integration user's key")
                for chunk in _chunks(missing):
                    left = CHECK_BUDGET - (self.clock() - t0)
                    if left < READ_LEAST:
                        raise ShopUnreadable("the prices took too long")
                    read = self.prices(shop["url"], shop["key"], plist, chunk, ctx.get("currency") or "",
                                       min(READ_TIMEOUT, left))
                    with self.lock:                 # each chunk kept as it comes: the next press reads only the rest
                        if len(self.lowest_cache) >= EXPIRY_MAX:
                            self.lowest_cache.clear()
                        for it in chunk:
                            mine = [r for r in read if r.get("item_code") == it]
                            self.lowest_cache[mine_key + (it,)] = (now, mine)
                            rows += mine
                            todo.remove(it)
            except ShopUnreadable:
                for it in todo:
                    if not (hits[it] and now - hits[it][0] < SETTINGS_STALE):
                        raise
                    rows += hits[it][1]
        return guard.lowest_prices(rows, ctx.get("currency") or "", self.today())

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
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(route_key)
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
        if path == "/tgr/check":
            refused = guard.refusal(ctx, rules)          # first, and from the settings alone: never lost to a price read
            if refused:
                return 200, refused
            try:
                lowest = self.lowest(name, shop, ctx, rules, t0)
            except ShopUnreadable:
                plain = guard.on_check(ctx, rules, {}, unchecked=True)   # a large sale still goes to its approval, saying so
                if plain["verdict"] != "allow":
                    return 200, plain
                return 503, {"error": "the shop's lowest prices cannot be read"}
            return 200, guard.on_check(ctx, rules, lowest)
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
    if not (oneshop.many(conf) or all(oneshop.value(conf, k) for k in ("IVN_CHECK_SECRET", "IVN_SCAN_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_CHECK_SECRET, IVN_SCAN_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), "
                         "or IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
