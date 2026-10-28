#!/usr/bin/env python3
"""S2 — the *Where is it?* till key on its own, for CitiXsys hosting (standard library only).

    POST /point/where_is_it   the till key's call (signed by the shop)   →  200 {"message": {...}}
    GET  /health              200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses. It is the till key alone: it READS the shop's bin records and writes nothing. ``app.py`` beside it is the
whole S2 service for your own server (sales take stock out of bins, putaway and pick); this file needs none of that.

A press names the sale's items and the till's store (the warehouse its till profile sells from). The answer names, for
each item, the bin the shop recorded for it: a shop-floor bin of that store first, else a back-room bin. The shop's
records are read fresh on every press, with the app's integration user's key, in two reads, each bounded by the store:
    <prefix> Location      the locations that serve the till's store
    <prefix> Item In Bin   the items on the sale (the first CODES_MAX of them), with a quantity above 0, at those
                           locations (its Location fills itself from its bin when the record is saved)
Both share one deadline inside the till's 3 seconds. When the app has no user's key yet, the shop refuses that key, the
shop cannot be read in time, or there are more records than one answer can take, the cashier is told so in words (200, a
warning message), never a guess. The till's message holds about ten items, so only the first CODES_MAX items of a sale
are looked up; the rest are counted in the message's "and N more" (bound: such a sale is coloured as a warning).
Bounds: a record saved before its Location field existed is found once it is saved again; the time limit is per socket
operation, so a shop that trickles its answer can take longer (the till then says it did not answer in time).

ONE SHOP (env or an env file):
    IVN_POINT_SECRET   the till key's secret (handed back at install as <app>:where_is_it)
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_bln), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the till key's secret and the key
                       of the app's own user (the install made it; "user:<email>"); every call names its shop
                       (X-iVendNext-Site).
BLN_PREFIX (default PP BLN; IVENDNEXT BLN for the library's app) · PORT (default 8080)

    python3 service/where.py [service/.env.local]
"""

from __future__ import annotations

import base64
import hashlib
import hmac
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
import core  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

ROUTE, KEY = "/point/where_is_it", "where_is_it"       # the manifest's remote_keys[].key; its secret is "<app>:<key>"
BODY_MAX, SKEW_S = 64 * 1024, 300
READ_TIMEOUT, DEADLINE = 0.8, 2.2      # each read, and all of them together: inside the till's 3 seconds
CODES_MAX, ROWS_MAX = 30, 1000      # items looked up; rows one read may return
NOT_SET_UP = ("Bin locations is not set up yet: no key from this shop has reached it. Ask your manager to check that the "
              "app's user has its key and, if the site could not reach the app, or a key was lost or changed, to press Connect again on the app.")
REFUSED = "Bin locations cannot read your bins. Ask your manager to check the app's user and press Connect again."
NO_RIGHTS = ("Bin locations' user may not read your bins. Ask your manager to let its role read Locations and "
             "What is in each bin.")
UNREADABLE = "The bins cannot be read right now. Try again in a moment."
TOO_MANY = "There are too many bin records to answer here. Open What is in each bin in Desk."


class ShopUnreadable(Exception):
    def __init__(self, why: str, code: int | None = None):
        super().__init__(why)
        self.code = code            # the shop's HTTP status, when it answered one


class TooMany(Exception):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def read_list(url: str, key: str, doctype: str, fields: list, filters: list, timeout: float = READ_TIMEOUT) -> list:
    """One list read over the record API, as the app's integration user."""
    q = urllib.parse.urlencode({"fields": json.dumps(fields), "filters": json.dumps(filters),
                                "limit_page_length": str(ROWS_MAX + 1)})   # one more: a cut list is seen
    req = urllib.request.Request(f"{url.rstrip('/')}/api/resource/{urllib.parse.quote(doctype)}?{q}",
                                 headers={"Authorization": f"token {key}", "Accept": "application/json"})
    try:
        with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
            data = (json.loads(r.read() or b"{}") or {}).get("data")
    except urllib.error.HTTPError as e:
        e.close()
        raise ShopUnreadable(f"the shop answered {e.code}", e.code) from None
    except (urllib.error.URLError, TimeoutError, ConnectionError, ValueError) as e:
        raise ShopUnreadable(type(e).__name__) from None
    if not isinstance(data, list):
        raise ShopUnreadable("not a list")
    return data


def first_codes(context: dict) -> list[str]:
    """The sale's first CODES_MAX distinct item codes, in the sale's order (all the message can show)."""
    out = []
    for line in context.get("lines") or []:
        code = line.get("item_code") if isinstance(line, dict) else None
        if code and str(code) not in out:
            out.append(str(code))
    return out[:CODES_MAX]


def bin_rows(read, prefix: str, context: dict) -> list[dict]:
    """The rows ``core.where_answer`` reads, for the items on the sale, at the till's own store only. ``TooMany`` when a
    read returns more than ROWS_MAX rows: a cut list would say "no bin recorded" for an item that has one."""
    codes, store = sorted(first_codes(context)), context.get("store")
    if not codes or not store:
        return []

    def rows(doctype, fields, filters):
        got = read(doctype, fields, filters)
        if len(got) > ROWS_MAX:
            raise TooMany(doctype)
        return got

    kind_of = {loc["name"]: loc.get("kind") for loc in rows(f"{prefix} Location", ["name", "kind", "store"], [["store", "=", store]])
               if loc.get("store") == store}           # the filter, held again here: never another store's bin
    if not kind_of:
        return []
    held = rows(f"{prefix} Item In Bin", ["item", "bin", "qty", "location"],
                [["item", "in", codes], ["qty", ">", 0], ["location", "in", sorted(kind_of)]])
    return [{"item": r["item"], "bin": r["bin"], "qty": r["qty"], "kind": kind_of[r["location"]]}
            for r in held if r.get("location") in kind_of]     # held again: never another store's bin


def verified(secrets: list[str], headers, raw: bytes) -> bool:
    """base64(HMAC-SHA256(secret, "<timestamp>.<raw body>")), a timestamp within five minutes (the template's check)."""
    ts, sig = headers.get("X-iVendNext-Timestamp") or "", headers.get("X-iVendNext-Signature") or ""
    if not (ts.isascii() and ts.isdigit()) or abs(time.time() - int(ts)) > SKEW_S:   # "²" is a digit int() refuses
        return False
    for secret in secrets:
        want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
        if hmac.compare_digest(want, sig.encode()):
            return True
    return False


def _warning(body: str) -> dict:
    return {"message": {"title": core.TITLE, "body": body, "level": "warning"}}


class Service:
    def __init__(self, conf: dict, store=None, reader=read_list, clock=time.monotonic):
        self.prefix = (conf.get("BLN_PREFIX") or "PP BLN").strip()
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.reader, self.clock = reader, clock
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secret = (conf.get("IVN_POINT_SECRET") or "").strip()
            if not self.secret:
                raise SystemExit("IVN_POINT_SECRET is empty: the app does not start without a way to check a call")
            self.shop = {"url": conf["IVN_SHOP_URL"], "key": conf["IVN_SHOP_KEY"]}

    def caller(self, headers) -> tuple[list[str], dict | None]:
        """(the secrets this call may be signed with, the shop's address and its integration user's key, if handed over)."""
        if not self.app:
            return [self.secret], self.shop
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:{KEY}")]
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        shop = {"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None
        return secrets, shop

    def _read(self, shop: dict, until: float):
        """A reader for one press: every read shares the press's deadline."""
        def read(doctype, fields, filters):
            left = until - self.clock()
            if left <= 0:
                raise ShopUnreadable("out of time")
            return self.reader(shop["url"], shop["key"], doctype, fields, filters, timeout=min(READ_TIMEOUT, left))
        return read

    def answer(self, headers, raw: bytes, note: dict) -> tuple[int, dict]:
        try:
            secrets, shop = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        if not secrets or not verified(secrets, headers, raw):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            context = json.loads(raw)["context"]
            if not isinstance(context, dict):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            return 400, {"error": "bad request"}
        if not any(line.get("item_code") for line in context.get("lines") or [] if isinstance(line, dict)):
            return 200, core.where_answer(context, [])     # an empty sale: nothing to look up
        if not shop:
            note["shop"] = "no user"
            return 200, _warning(NOT_SET_UP)
        try:
            rows = bin_rows(self._read(shop, self.clock() + DEADLINE), self.prefix, context)
        except TooMany:
            note["shop"] = "too many"
            return 200, _warning(TOO_MANY)
        except ShopUnreadable as e:
            note["shop"] = e.code or "unreadable"
            words = {401: REFUSED, 403: NO_RIGHTS}.get(e.code, UNREADABLE)   # neither mends by waiting
            return 200, _warning(words)
        except (KeyError, TypeError):
            note["shop"] = "bad answer"
            return 200, _warning(UNREADABLE)
        return 200, core.where_answer(context, rows)

    def handle(self, method: str, path: str, headers, raw: bytes | None, note: dict | None = None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this. ``note`` gets why a
        press could not read the shop (a status or a word, never a value), for the log line."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path != ROUTE:
            return 404, {"error": "not found"}
        return self.answer(headers, raw, {} if note is None else note)


def _log(log, rid: str, path: str, code: int, t0: float, note: dict | None = None):
    """One line per call: never the body, the context, a secret or a signature. ``shop`` says why the shop was not read."""
    line = {"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}
    log.write(json.dumps({**line, **(note or {})}) + "\n")
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
            t0, rid, code, note = time.monotonic(), (self.headers.get("X-iVendNext-Request-Id") or "-")[:40], 500, {}
            try:
                n = int(self.headers.get("Content-Length") or 0)
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= BODY_MAX else None, note)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0, note)

        def do_GET(self):
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the framework's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line."""
    t0, note = time.monotonic(), {}
    code, out = svc.handle(method, path, headers, raw, note)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0, note)
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
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_POINT_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_POINT_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), or IVN_LIBRARY_APP with a store "
                         "(many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
