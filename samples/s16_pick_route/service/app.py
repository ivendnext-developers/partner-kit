"""S16 — *Assign pick route*: the partner's service behind the shop's Desk button (standard library only).

    POST /press/route   the shop's signed press (``desk_action/1``)  →  200 {"message": …, "open_record": …}
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

For each Sales Order in the press it creates ONE pick task over the record API, with the app's own integration user's
key (that user's rights, never the pressing user's), then answers. A retry of the same press (the same
``idempotency_key``, which the shop keeps for a retry from the same dialog) finds the task it already made and makes no
second one: the key is stored on the task, so this holds across a restart. While one call handles a press, a second
call with the same key is refused (409): one shop's press is held by an in-process lock, many shops' by a claim in the
shops table that every copy of the function sees (``CLAIM_STALE``).

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``POST /test/mode`` picks the answer (``open`` · ``refresh`` · ``missing``) and
``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_POINT_SECRET (handed back at install as pp_pck:sub:route),
    PP_ADMIN_TOKEN, PP_PORT (8131)
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_pck), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the press's secret
                       (<app>:sub:route) and, once the shop has chosen it on the app's feed, its integration user's key
                       ("user:<email>"); every call names its shop (X-iVendNext-Site).
PCK_PREFIX (default PP PCK; IVENDNEXT PCK for the library's app) · PORT (default 8080)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import hashlib
import http.client
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import route  # noqa: E402
import shops  # noqa: E402

SUB = "route"           # the manifest's extension_subscriptions[].key; its secret is "<app>:sub:route"
CLAIM_STALE = 60        # a press's claim older than this is taken over: a function copy lives at most 10 s
ORDERS_MAX = 20         # orders one press may carry here: one find and a create each fit the function's 10 s
TOO_MANY = f"Pick route takes at most {ORDERS_MAX} orders at a time. Select fewer orders and press again."
NOT_SET_UP = ("Pick route is not set up yet. Ask your manager to choose its user on the app's feed and press "
              "Connect again.")
REFUSED = "Pick route may not write pick tasks. Ask your manager to check the app's user, its role and its API key."
CONNECT_AGAIN = " Then press Connect again on the app."    # many shops: a new key reaches the service only that way


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None):
        super().__init__(msg)
        self.code = code            # the shop's HTTP status, when it answered one


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


class Tenant:
    """The service's only door into iVendNext: the record API, as the integration user (token key:secret)."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 3):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _call(self, method: str, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/{urllib.parse.quote(path)}"
        if params:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) for k, v in params.items()})
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            e.close()
            raise TenantError(f"{method} {path} -> HTTP {e.code}", e.code) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {path} -> {type(e).__name__}") from None     # no status: the outcome is unknown

    def find_tasks(self, sales_orders: list[str], key: str) -> dict:
        """The tasks this press already made, by Sales Order: one read for the whole press."""
        try:
            rows = self._call("GET", route.TASK, {"filters": [["sales_order", "in", sales_orders], ["press_key", "=", key]],
                                                  "fields": ["name", "sales_order", "picker", "priority"],
                                                  "limit_page_length": 0})["data"]     # every row: never cut one off
            return {r["sales_order"]: r for r in rows}
        except (KeyError, TypeError):
            raise TenantError(f"GET {route.TASK} -> an answer with no rows") from None

    def create_task(self, doc: dict) -> str:
        try:
            return self._call("POST", route.TASK, body=doc)["data"]["name"]
        except (KeyError, TypeError):
            raise TenantError(f"POST {route.TASK} -> an answer with no name") from None     # it may have been made


def tenant_of(url: str, key: str) -> Tenant:
    """A shop's door from the key it handed over on Connect again ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str) -> dict:
    return {"message": {"title": "Pick route", "body": body, "level": "warning"}}


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, clock=time.time):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("PCK_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's names are not the sample's: every write would fail
            raise SystemExit("IVN_LIBRARY_APP is set but PCK_PREFIX is not (IVENDNEXT PCK for the App library's app)")
        route.use_prefix(prefix or "PP PCK")
        self.tenants, self.clock = tenants, clock
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secret, self.tenant = conf["PP_POINT_SECRET"], tenant
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.mode, self.received = "open", []
        self._lock = threading.Lock()     # one shop: one press at a time, so a retry racing its first try finds its task

    def caller(self, headers) -> tuple[str, list[str], object | None]:
        """(the shop's name, the secrets its press may be signed with, its door: None until it handed over a user's key)."""
        if not self.app:
            return "-", [self.secret], self.tenant
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{SUB}")]
        users = sorted(k for k in (record or {}).get("secrets") or {}
                       if k.startswith("user:") and k != "user:Administrator")    # the site never sends it; nor do we use it
        door = self.tenants(record["url"], record["secrets"][users[0]]) if record and users else None
        return site or "", secrets, door

    @contextmanager
    def held(self, site: str, key: str):
        """``{"mine": True}`` while this call alone handles the press ``key`` of ``site``; ``mine`` False when another call
        holds it. The caller sets ``keep`` when a write's outcome is unknown (the shop may still save a task): the claim is
        then left to go stale, so a retry within CLAIM_STALE is refused instead of making a second task."""
        state = {"mine": True, "keep": False}
        if not self.app:
            with self._lock:
                yield state
            return
        name = f"press{shops.CLAIM_MARK}{site}{shops.CLAIM_MARK}{hashlib.sha256(key.encode()).hexdigest()[:32]}"
        if not self.store.claim(name, self.clock(), CLAIM_STALE):
            state["mine"] = False
            yield state
            return
        try:
            yield state
        finally:
            if not state["keep"]:
                try:
                    self.store.delete(name)
                except Exception:   # noqa: BLE001 — the press is answered; a claim left behind goes stale in CLAIM_STALE
                    pass

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(route.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            ctx = route.context_of(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [ctx])[-20:]
        inputs, key = ctx["inputs"], ctx["idempotency_key"]
        tasks = [route.plan(r, inputs, key) for r in ctx["records"]]
        if self.mode == "missing":
            return 200, route.answer(tasks, [], "missing")
        if door is None:
            return 200, _warning(NOT_SET_UP)
        if len(tasks) > ORDERS_MAX:
            return 200, _warning(TOO_MANY)
        names = []
        try:
            with self.held(site, key) as held:
                if not held["mine"]:
                    return 409, {"error": "this press is being handled; check the record before you try again"}
                writing = False
                try:
                    found = door.find_tasks([t["sales_order"] for t in tasks], key)
                    for t in tasks:
                        row = found.get(t["sales_order"])
                        if row:    # a retry: answer about the task that exists, even if the dialog's inputs changed
                            t.update(picker=row["picker"], priority=row["priority"])
                        else:
                            writing = True
                        names.append(row["name"] if row else door.create_task(t))
                except TenantError as e:
                    # a write with no answer: the shop may still save the task, so the claim stays (a read frees it)
                    held["keep"] = writing and e.code is None
                    raise
        except TenantError as e:
            if e.code in (401, 403):    # the shop refused the app's user: say so; a task the call made stays found
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            # the shop tells the user "did not answer in time. Check the record before you try again": true, because
            # a task may already exist; the same key's retry finds it (or, while the claim stands, is refused)
            return 502, {"error": str(e)}
        except Exception:               # noqa: BLE001 — the shops table did not answer the claim: nothing was written
            return 503, {"error": "unavailable"}
        return 200, route.answer(tasks, names, self.mode)

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > route.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path == "/press/route":
            return self.press(headers, raw)
        return 404, {"error": "not found"}


def _log(log, rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a secret or a signature."""
    log.write(json.dumps({"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
    log.flush()


def make_handler(svc: Service, log=sys.stderr):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _send(self, code: int, body: dict):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _admin(self) -> bool:
            return svc.test_modes and self.headers.get("X-PP-Admin") == svc.admin

        def do_POST(self):
            t0, rid, code = time.monotonic(), (self.headers.get("X-iVendNext-Request-Id") or "-")[:40], 500
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 <= n <= route.BODY_MAX:
                    code = 413
                    return self._send(413, {"error": "too large"})
                raw = self.rfile.read(n)
                if self.path == "/test/mode" and self._admin():
                    mode = json.loads(raw or b"{}").get("mode")
                    if mode in ("open", "refresh", "missing"):
                        svc.mode, code = mode, 200
                        return self._send(200, {"mode": mode})
                code, out = svc.handle("POST", self.path, self.headers, raw)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            if self.path == "/test/received" and self._admin():
                return self._send(200, {"received": svc.received})
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the framework's own access line carries the path; keep it off
            pass

    return Handler


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b): settings from the environment.
lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle)


def env(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env(sys.argv[1]) if len(sys.argv) > 1 else {}))
    if conf.get("IVN_LIBRARY_APP"):
        svc = Service(conf)
    elif all(conf.get(k) for k in ("PP_BASE", "PP_KEY", "PP_SECRET", "PP_POINT_SECRET")):
        svc = Service(conf, Tenant(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    else:
        raise SystemExit("set PP_BASE, PP_KEY, PP_SECRET and PP_POINT_SECRET (one shop), or IVN_LIBRARY_APP with a store "
                         "(many shops): the app does not start without a way to check a press")
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8131)), make_handler(svc))
    print(f"s16 pick route on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"{route.TASK}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
