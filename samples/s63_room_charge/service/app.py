#!/usr/bin/env python3
"""S63 — *Room charge*: the service between a hotel's tills and its property system (standard library only).

    POST /rmc/check    the check at Pay (``check/1``): the room and surname confirmed with the hotel system, the reservation
                       filled as Folio, the Room Charge tile dimmed with its reason when they do not fit
    GET  /health
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

After the sale the worker (``worker.py``) reads the shop's event feed and posts the charge to the folio.

WHERE EACH HOTEL'S CONNECTION IS KEPT. In the shop's own iVendNext, the settings record ``PP RMC Settings``, one row per
store, read at every call with the key of the shop whose signature the call carries.

ONE SHOP (env or an env file): IVN_CHECK_SECRET (handed back at install as pp_rmc:sub:room) · IVN_SHOP_URL · IVN_SHOP_KEY
("<api key>:<api secret>", the app's own user)
MANY SHOPS (guide chapter 1a): IVN_LIBRARY_APP with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE
RMC_PREFIX (default PP RMC) · HOTEL_SIM_URL (the stand-in, to try it with no hotel system) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import hmac
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import hotel as H  # noqa: E402
import oneshop  # noqa: E402
import rooms  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402
from shop import Shop, ShopError  # noqa: E402

CHECK, ROUTE = "room", "/rmc/check"      # the check's key in the manifest, and its address
SKEW_S, READ_TIMEOUT, HOTEL_TIMEOUT = 300, 0.9, 1.5        # one read of the shop and the hotel call, inside the till's 3 seconds


def verify(timestamp, signature, raw: bytes, secret: str, now=None) -> bool:
    """True when the call is the shop's: base64 HMAC-SHA256 of ``<timestamp>.<raw body>``."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return False
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    return hmac.compare_digest(want, sig.encode())


def user_key(record: dict) -> tuple[str, str]:
    """The app user's key the shop handed over at connect ("user:<email>": "<key>:<secret>")."""
    users = sorted(k for k in record.get("secrets") or {} if k.startswith("user:"))
    if not users or ":" not in record["secrets"][users[0]]:
        raise ShopError(0, "the shop has not handed over its app user's key")
    key, secret = record["secrets"][users[0]].split(":", 1)
    return key, secret


class Service:
    def __init__(self, conf: dict, store=None, opener=None):
        self.conf = conf
        self.prefix = (conf.get("RMC_PREFIX") or "PP RMC").strip()
        self.app = oneshop.value(conf, oneshop.MANY)
        self.opener = opener or (lambda url, key, secret, timeout: Shop(url, key, secret, timeout))
        if self.app:                                            # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                                   # one shop, from the settings
            one = oneshop.settings(conf, ["IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_CHECK_SECRET"])
            key, secret = one["IVN_SHOP_KEY"].split(":", 1)
            self.one = {"site": "-", "url": one["IVN_SHOP_URL"].rstrip("/"), "key": key, "secret": secret,
                        "check": one["IVN_CHECK_SECRET"]}

    def caller(self, headers) -> tuple[dict | None, list[str]]:
        """(the shop: its address and app user's key, the secrets this call may be signed with)."""
        if not self.app:
            return self.one, [self.one["check"]]
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{CHECK}")]
        if not record:
            return None, secrets
        try:
            key, secret = user_key(record)
        except ShopError:
            return {"site": site, "url": record["url"], "key": "", "secret": ""}, secrets
        return {"site": site, "url": record["url"], "key": key, "secret": secret}, secrets

    def shop(self, who: dict, timeout: float = READ_TIMEOUT):
        if not who.get("key"):
            raise ShopError(0, "the shop has not handed over its app user's key")
        return self.opener(who["url"], who["key"], who["secret"], timeout)

    def settings(self, t) -> dict:
        name = f"{self.prefix} Settings"
        return rooms.settings_of(t.get(name, name))     # one record, named as its record type

    def answer(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            who, secrets = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or not any(verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a shop the app does not know
        if testcall.is_test(headers):               # checked as a real call; the check itself does not run
            return testcall.answer(CHECK)
        try:
            ctx = json.loads(raw)["context"]
        except (ValueError, KeyError, TypeError):
            return 400, {"error": "not a call from the till"}
        try:
            stores = self.settings(self.shop(who))
        except ShopError as e:          # the shop could not be read: the till applies the check's down answer
            print(json.dumps({"site": who.get("site"), "error": f"shop {e.status}"}), file=sys.stderr, flush=True)
            return 503, {"error": "the shop cannot be read"}
        return 200, self.check(ctx, stores.get(ctx.get("store") or ""))

    def check(self, ctx: dict, s: dict | None) -> dict:
        mode = (s or {}).get("mode") or rooms.MODE
        if ctx.get("stage") != "sale":
            return rooms.check_return(ctx, mode)
        if not s:                       # a store with no hotel link: the tile is the shop's own, with no check
            return {"verdict": "allow"}
        answer, room, guest = rooms.check_sale(ctx, mode)
        if answer:
            return answer
        try:
            return rooms.found(H.adapter(self.conf, s, HOTEL_TIMEOUT).find(room, guest), room, guest)
        except H.HotelDown:
            return rooms.hotel_down(room)
        except H.HotelRefused as e:
            return rooms.not_confirmed(mode, str(e))

    def handle(self, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path == ROUTE:
            return self.answer(headers, raw)
        return 404, {"error": "not found"}


def _log(rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a secret or a signature."""
    print(json.dumps({"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}), flush=True)


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log((headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


def scheduled(svc: Service, name: str, seconds: float = 900, now: datetime.datetime | None = None) -> dict:
    """One scheduled pass (CitiXsys hosting runs the app as a function): the shops this call claims, each to its end."""
    import worker
    store = function.Claimed(svc.store, seconds)
    return worker.pass_all(svc, store, deadline=seconds + 60, finished=store.release)


lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle, scheduled)


def make_server(svc: Service, port: int):
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
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n)
            self._send(*handle(svc, "POST", self.path, self.headers, raw))

        def do_GET(self):
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the framework's own access line; ours is _log
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def env_file(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env_file(sys.argv[1]) if len(sys.argv) > 1 else {}))
    if not (oneshop.many(conf) or all(oneshop.value(conf, k) for k in ("IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_CHECK_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop) or IVN_LIBRARY_APP with a store (many shops)")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    import worker
    threading.Thread(target=worker.serve, args=(svc,), daemon=True).start()   # the feed, beside the till
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "many": bool(svc.app)}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
