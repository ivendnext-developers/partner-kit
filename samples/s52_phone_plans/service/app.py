#!/usr/bin/env python3
"""S52 — *Phone plans from a telecom company*: the service between the retailer's till and a telecom company (standard
library only).

    POST /tel/plans    the Plans till key (remote till key)  ->  200 {"message": ...}: the plans and prices for the phone
                       on the sale and this customer, from the telecom company, with THIS retailer's telecom account
    POST /tel/check    the check at Pay (``check/1``)  ->  allow, or refuse in plain words: each plan line confirmed with
                       the telecom company (the plan fits a phone on the sale, this customer may take it, its price holds)
    GET  /health
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

After payment the worker (``worker.py``) reads the retailer's event feed, activates each paid plan with the telecom
company and writes the number to a ``PP TEL Activation`` row of the sale (shown under the sale's Connections); it also
keeps the plans' prices on the retailer's price list in step with the telecom company's.

WHERE EACH RETAILER'S TELECOM ACCOUNT IS KEPT. In the retailer's own iVendNext: the settings record ``PP TEL Settings``
record ``Default`` (``telecom_account``, ``telecom_key``), which only the System Manager and the app's own role
read. The service reads it
at every call with the key of the retailer whose signature the call carries, and keeps nothing between calls but the
shops store (each retailer's address and the secrets its install handed over). So one retailer's call can only ever be
answered with that retailer's account: the address, the key and the account all come from the record its signature
matched.

ONE RETAILER (env or an env file):
    IVN_POINT_SECRET   the Plans key's secret (handed back at install as pp_tel:pp_tel_plans)
    IVN_CHECK_SECRET   the check's secret (handed back at install as pp_tel:sub:plans)
    IVN_SHOP_URL       the retailer's address, e.g. https://retailer.example.com
    IVN_SHOP_KEY       the app's own user's key, "<api key>:<api secret>"
MANY RETAILERS (guide chapter 14b): IVN_LIBRARY_APP (the App library's id) with IVN_SHOPS_TABLE (CitiXsys hosting) or
    IVN_SHOPS_FILE. Each retailer connects itself after its install and hands over the two secrets
    ("<app>:<app>_plans", "<app>:sub:plans") and its app user's key ("user:<email>": "<api key>:<api secret>").
TEL_API (the telecom company's address; the stand-in: http://127.0.0.1:8154) · TEL_PREFIX (default PP TEL) ·
PP_STATE (a folder for the feed's handled-events note) · PORT (default 8080)

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
import plans  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402
import telecom  # noqa: E402
from shop import Shop, ShopError  # noqa: E402

KEY, CHECK = "plans", "plans"            # the till key's and the check's keys in the manifest
PLANS, CHECKS = "/tel/plans", "/tel/check"
SKEW_S, READ_TIMEOUT = 300, 0.9          # one read of the retailer inside the till's 3 seconds, and one telecom call


def verify(timestamp, signature, raw: bytes, secret: str, now=None) -> bool:
    """True when the call is the retailer's: base64 HMAC-SHA256 of ``<timestamp>.<raw body>`` (as in S18, S22, S51)."""
    ts, sig = timestamp or "", signature or ""
    if not (ts.isascii() and ts.isdigit()) or abs((now or time.time()) - int(ts)) > SKEW_S:
        return False
    want = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest())
    return hmac.compare_digest(want, sig.encode())


def user_key(record: dict) -> tuple[str, str]:
    """The app user's key the retailer handed over at connect ("user:<email>": "<key>:<secret>")."""
    users = sorted(k for k in record.get("secrets") or {} if k.startswith("user:"))
    if not users or ":" not in record["secrets"][users[0]]:
        raise ShopError(0, "the retailer has not handed over its app user's key")
    key, secret = record["secrets"][users[0]].split(":", 1)
    return key, secret


class Service:
    def __init__(self, conf: dict, store=None, opener=None):
        self.conf = conf
        self.prefix = (conf.get("TEL_PREFIX") or "PP TEL").strip()
        self.tel_api = (conf.get("TEL_API") or "").strip()
        self.app = oneshop.value(conf, oneshop.MANY)
        # the till key as the site knows it (the manifest's remote_keys[].key): <app>_plans, or the sample's pp_tel_plans
        self.till_key = f"{self.app or self.prefix.lower().replace(' ', '_')}_{KEY}"
        self.opener = opener or (lambda url, key, secret, timeout: Shop(url, key, secret, timeout))
        if self.app:                                            # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                                   # one retailer, from the settings
            one = oneshop.settings(conf, ["IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_POINT_SECRET", "IVN_CHECK_SECRET"])
            key, secret = one["IVN_SHOP_KEY"].split(":", 1)
            self.one = {"site": "-", "url": one["IVN_SHOP_URL"].rstrip("/"), "key": key, "secret": secret,
                        PLANS: one["IVN_POINT_SECRET"], CHECKS: one["IVN_CHECK_SECRET"]}

    # ---- who is calling ------------------------------------------------------------------------------------------
    def caller(self, route: str, headers) -> tuple[dict | None, list[str]]:
        """(the retailer: its address and app user's key, the secrets this route may be signed with)."""
        if not self.app:
            return self.one, [self.one[route]]
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        name = f"{self.app}:{self.till_key}" if route == PLANS else f"{self.app}:sub:{CHECK}"
        secrets = [s.decode() for s in shops.secrets_for(record, name)]
        if not record:
            return None, secrets
        try:
            key, secret = user_key(record)
        except ShopError:
            return {"site": site, "url": record["url"], "key": "", "secret": ""}, secrets
        return {"site": site, "url": record["url"], "key": key, "secret": secret}, secrets

    def shop(self, who: dict, timeout: float = READ_TIMEOUT):
        if not who.get("key"):
            raise ShopError(0, "the retailer has not handed over its app user's key")
        return self.opener(who["url"], who["key"], who["secret"], timeout)

    def settings(self, t) -> dict:
        return plans.settings_of(t.get(f"{self.prefix} Settings", "Default"))   # one record, named Default

    def telecom(self, s: dict, timeout: float = 1.5) -> telecom.Telecom:
        return telecom.Telecom(self.tel_api, s["account"], s["key"], timeout)

    # ---- the till's two calls ------------------------------------------------------------------------------------
    def answer(self, route: str, headers, raw: bytes) -> tuple[int, dict]:
        try:
            who, secrets = self.caller(route, headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or not any(verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a retailer the app does not know
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(self.till_key if route == PLANS else CHECK)
        try:
            body = json.loads(raw)
            ctx = body["context"]
        except (ValueError, KeyError, TypeError):
            return 400, {"error": "not a call from the till"}
        if route == CHECKS and (not ctx.get("lines") or (ctx.get("stage") != "sale" and not any(
                int((ln or {}).get("qty_milli") or 0) > 0 for ln in ctx["lines"]))):
            return 200, {"verdict": "allow"}       # nothing sold, or a return that sells nothing: nothing to read
        try:
            s = self.settings(self.shop(who))
        except ShopError as e:          # the retailer could not be read: the till applies the check's down answer
            print(json.dumps({"site": who.get("site"), "error": f"shop {e.status}"}), file=sys.stderr, flush=True)
            return 503, {"error": "the retailer cannot be read"}
        if route == PLANS:
            return 200, self.plans_key(ctx, s)
        return 200, self.check(ctx, s)

    def plans_key(self, ctx: dict, s: dict) -> dict:
        customer = ctx.get("customer") or None
        try:
            answer = self.telecom(s).offers(plans.phones_on(ctx.get("lines")), customer)
        except telecom.TelecomDown:
            return plans.down_message()
        except telecom.TelecomRefused as e:
            return {"message": {"title": "Telecom company refused", "body": plans.plain(str(e), 280), "level": "warning"}}
        return plans.plans_message(answer, customer, ctx.get("currency") or "")

    def check(self, ctx: dict, s: dict) -> dict:
        if not plans.plan_lines(ctx, s) or ctx.get("stage") != "sale":
            return plans.check(ctx, s, None)        # the telecom company is not asked: no plan, or an exchange's plan refused
        try:
            return plans.check(ctx, s, lambda phones, customer: self.telecom(s).offers(phones, customer))
        except telecom.TelecomDown:
            return plans.refuse("The telecom company is not answering, so the plan can't be confirmed. Try again, or "
                                "take the plan off the sale.")
        except telecom.TelecomRefused as e:
            return plans.refuse(f"The telecom company refused: {e}")

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > plans.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path in (PLANS, CHECKS):
            return self.answer(path, headers, raw)
        return 404, {"error": "not found"}


def _log(rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a secret or a signature."""
    print(json.dumps({"request": rid, "route": path[:40], "status": code,
                      "ms": int((time.monotonic() - t0) * 1000)}), flush=True)


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log((headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


def scheduled(svc: Service, name: str, seconds: float = 900, now: datetime.datetime | None = None) -> dict:
    """One scheduled pass (CitiXsys hosting runs the app as a function): the retailers this call claims, each to its end
    (its feed, then its prices), each claim freed as its retailer finishes."""
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
            raw = self.rfile.read(n) if 0 <= n <= plans.BODY_MAX else None
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
    one = ("IVN_POINT_SECRET", "IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY")
    if not (oneshop.many(conf) or all(oneshop.value(conf, k) for k in one)) or not conf.get("TEL_API"):
        raise SystemExit("set TEL_API, and IVN_POINT_SECRET, IVN_CHECK_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one retailer) "
                         "or IVN_LIBRARY_APP with a store (many retailers)")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    import worker
    threading.Thread(target=worker.serve, args=(svc,), daemon=True).start()   # the feed and the prices, beside the till
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "many": bool(svc.app)}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
