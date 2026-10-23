#!/usr/bin/env python3
"""S48 — *Customer code check*: the service behind the shop's capture on customer select (standard library only).

    POST /ccc/capture  the shop's signed select (``capture/1``, event ``customer_select``) and the code the customer read
                       out (event ``verify``), one address for both
                       →  200 {"verdict": "allow"} | {"verdict": "challenge", "prompt": "...", "length": 6}
                          | {"verdict": "refuse", "reason": "..."} | {"verdict": "ok"}
    GET  /health       200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers picks and codes. The shape is S47's (``samples/s47_customers_by_store/service/app.py``), copied: a defect there is a
defect here.

The call is checked with the secret the install made for the capture, ``<app>:sub:on_select``. On a select, the shop's
switched-on rule records (``<prefix> Rule``) and its Customer Group tree are read at the same time with the app's
integration key and kept one minute (``RULES_TTL``). When the rule asks, the service makes a code and **creates** the shop's code record (``<prefix> Code``,
named by the till's ``challenge_id``); the shop's own Notification on that record texts the code to the number it holds,
inside the same save (a gateway that fails is written to the shop's Error Log, never raised: the customer then has no code). On a verify, it reads that record, and on a right code
**updates** it once (*Used*, the code cleared). The service never reads the Customer record and keeps no code: the code
lives in the shop's record only.

When the shop cannot be read or written, has not handed over its integration user's key yet,
or refuses the key (401 or 403: a key withdrawn, a user disabled, a right not given), the service answers 503 and the till
applies the subscription's down answer (``allow_and_flag`` in this manifest: the customer stays on the sale, which is
flagged; a shop that must never let a customer on without their code sets the down answer to ``refuse``).

ONE SHOP (env or an env file):
    IVN_CAPTURE_SECRET the capture's secret (handed back at install as pp_ccc:sub:on_select)
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_ccc), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the capture's secret and its integration
                       user's key ("user:<email>": "<api key>:<api secret>"); every call names its shop (X-iVendNext-Site).
CCC_PREFIX (default PP CCC; IVENDNEXT CCC for the library's app) · PORT (default 8080)

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
import codecheck  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

KEY, ROUTE = "on_select", "/ccc/capture"   # the subscription's key in the manifest; its secret is "<app>:sub:<key>"
RULES_TTL = 60
READ_TIMEOUT = 0.8     # the rules and the tree go at once, then the write: all inside the capture's 5 s (the manifest)
WRITE_TIMEOUT = 2.5    # the code record's save carries the shop's text to its gateway: at most this long ...
BUDGET = 3.5           # ... and never past this many seconds from the call's start (a late save still answers the field)
VERIFY_TIMEOUT = 2.0   # the code record's read on a verify: a busy shop is not a 503 (the till lets any code in on one)


class ShopUnreadable(Exception):
    """The shop did not answer with records, or did not save one: nothing was judged, so the till applies the down
    answer."""


class KeyRefused(ShopUnreadable):
    """The shop answered 401 or 403 to the app's user key (a key withdrawn, a user disabled, a right not given): judged as
    the shop unreadable, but logged by its own name, so a partner can tell it from an outage."""


class WriteUnsure(ShopUnreadable):
    """A write sent whole whose answer did not come in time: it may have saved (and texted the code) or not. A code
    record unsure is answered with the code field: saved, the code works; not saved, the check ends. Never a 503,
    which lets the customer on with no code."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


class ShopApi:
    """The reads and writes the service makes, with the shop's own key. Swapped for a stand-in in the tests."""

    def _call(self, url: str, key: str, path: str, query: dict | None = None, body: dict | None = None,
              method: str = "GET", timeout: float = READ_TIMEOUT, missing_ok: bool = False):
        q = f"?{urllib.parse.urlencode(query)}" if query else ""
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Authorization": f"token {key}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(f"{url.rstrip('/')}{path}{q}", data=data, headers=headers, method=method)
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            e.close()
            if missing_ok and e.code == 404:
                return None
            raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)(f"the shop answered {e.code}") from None
        except TimeoutError as e:       # sent whole, no answer in time (a connect timeout comes as a URLError, below)
            raise (WriteUnsure if data is not None else ShopUnreadable)(type(e).__name__) from None
        except (OSError, http.client.HTTPException, ValueError) as e:   # OSError: URLError, timeouts, TLS, a cut
            raise ShopUnreadable(type(e).__name__) from None             # connection; HTTPException: a cut answer

    def _list(self, url: str, key: str, doctype: str, fields, filters: list, limit: int = 0):
        out = self._call(url, key, "/api/resource/" + urllib.parse.quote(doctype),
                         {"fields": json.dumps(list(fields)), "filters": json.dumps(filters), "limit_page_length": limit})
        return out.get("data") if isinstance(out, dict) else None

    def rules(self, url: str, key: str, prefix: str) -> list:
        """The shop's switched-on Rule records (every one: ``limit_page_length`` 0)."""
        return self._list(url, key, prefix + " Rule", codecheck.RULE_FIELDS, [["enabled", "=", 1]])

    def tree(self, url: str, key: str) -> list:
        """The shop's Customer Group tree: every group's ``lft`` and ``rgt``."""
        return self._list(url, key, "Customer Group", codecheck.TREE_FIELDS, [])

    def create(self, url: str, key: str, prefix: str, record: dict, timeout: float = WRITE_TIMEOUT) -> None:
        """The code record: the shop's Notification on it texts the code inside this save (a failed text is logged by the shop,
        not raised)."""
        self._call(url, key, "/api/resource/" + urllib.parse.quote(prefix + " Code"), body=record, method="POST",
                   timeout=timeout)

    def code(self, url: str, key: str, prefix: str, name: str) -> dict | None:
        """The code record the till's ``challenge_id`` names, or ``None`` when there is none."""
        out = self._call(url, key, f"/api/resource/{urllib.parse.quote(prefix + ' Code')}/{urllib.parse.quote(name)}",
                         missing_ok=True, timeout=VERIFY_TIMEOUT)
        if out is None:
            return None
        rec = out.get("data") if isinstance(out, dict) else None
        if not isinstance(rec, dict):
            raise ShopUnreadable("not a record")
        return {k: rec.get(k) for k in codecheck.CODE_FIELDS}

    def used(self, url: str, key: str, prefix: str, name: str, now: int) -> None:
        """A right code, spent: *Used*, the code cleared, and when."""
        self._call(url, key, f"/api/resource/{urllib.parse.quote(prefix + ' Code')}/{urllib.parse.quote(name)}",
                   body={"status": codecheck.USED, "code": "", "verified_at": now}, method="PUT")


class Service:
    def __init__(self, conf: dict, store=None, api=None, clock=time.monotonic, wall=time.time):
        self.prefix = (conf.get("CCC_PREFIX") or "PP CCC").strip()
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.api, self.clock, self.wall, self.kept, self.lock = api or ShopApi(), clock, wall, {}, threading.Lock()
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secret = conf["IVN_CAPTURE_SECRET"]
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

    def _kept(self, name: str, shop: dict):
        now = self.clock()
        with self.lock:
            hit = self.kept.get(name)
        if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:
            return hit[2]
        return None

    def select(self, name: str, shop: dict | None, ctx: dict, t0: float | None = None) -> dict:
        """One pick: the rules and the tree read at the same time (each read has its own timeout, so reads in a row could
        outrun the select's time); then, when the rule asks, the code record written before the challenge is answered."""
        if not shop:
            raise ShopUnreadable("the shop has not handed over its integration user's key")
        now = int(self.wall())
        kept = self._kept(name, shop)
        if kept is None:
            with ThreadPoolExecutor(max_workers=2) as pool:
                rows = pool.submit(self.api.rules, shop["url"], shop["key"], self.prefix)
                groups = pool.submit(self.api.tree, shop["url"], shop["key"])
                kept = (codecheck.rules_of(rows.result()), codecheck.tree_of(groups.result()))
            with self.lock:
                self.kept[name] = (self.clock(), shop["key"], kept)
        out = codecheck.on_select(ctx, *kept)
        if out["verdict"] == "challenge":
            try:
                left = BUDGET - (self.clock() - (self.clock() if t0 is None else t0))
                self.api.create(shop["url"], shop["key"], self.prefix, codecheck.code_record(ctx, codecheck.new_code(), now),
                                timeout=max(0.5, min(WRITE_TIMEOUT, left)))
            except WriteUnsure:         # saved or not, the code field fails closed: never a 503 that lets them on
                print(json.dumps({"error": "WriteUnsure"}), file=sys.stderr, flush=True)
        return out

    def verify(self, shop: dict | None, ctx: dict) -> dict:
        if not shop:
            raise ShopUnreadable("the shop has not handed over its integration user's key")
        now = int(self.wall())
        rec = self.api.code(shop["url"], shop["key"], self.prefix, ctx["challenge_id"])
        out = codecheck.on_verify(ctx, rec, now)
        if out["verdict"] == "ok":
            self.api.used(shop["url"], shop["key"], self.prefix, ctx["challenge_id"], now)
        return out

    def answer(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if path != ROUTE:
            return 404, {"error": "not found"}
        t0 = self.clock()
        try:
            name, secrets, shop = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(codecheck.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            ctx = codecheck.capture_context(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        try:
            if ctx["event"] == "verify":
                return 200, self.verify(shop, ctx)
            return 200, self.select(name, shop, ctx, t0)
        except (ShopUnreadable, ValueError) as e:       # the shop did not answer, or not with records: nothing was judged
            with self.lock:
                self.kept.pop(name, None)               # a group the kept tree does not know is read again next time
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "the shop cannot be read"}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > codecheck.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.answer(path, headers, raw)


def _log(log, rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a code, a secret or a signature."""
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
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= codecheck.BODY_MAX else None)
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
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_CAPTURE_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_CAPTURE_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), "
                         "or IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
