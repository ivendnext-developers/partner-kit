"""S35 — *Send to store*: the partner's service behind the shop's Desk button (standard library only).

    POST /press/route   the shop's signed press (``desk_action/1``)  →  200 {"message": …, "refresh": true}
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

For the one draft Sales Order in the press it reads the order with the app's own integration user's key (that user's
rights, never the pressing user's), walks the order's territory up the tree to the first Serving store, and writes that
warehouse on the order and on every line, then answers. The write carries the order's ``modified`` as read, so the
shop refuses it if the order changed meanwhile; the service reads it once more without writing, answers Already if a
second press routed it meanwhile, and otherwise asks the agent to reload: it never writes over someone's edit. A press repeated (a retry, a second click, two copies of the function) finds the order already routed
and writes nothing: the routing is the same every time, so no press needs remembering. The shop's save may change the
total (a store's own item tax, a price limited to a warehouse): the answer then says so.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_POINT_SECRET (handed back at install as pp_cco:sub:route),
    PP_ADMIN_TOKEN, PP_PORT (8147)
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_cco), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the press's secret
                       (<app>:sub:route) and the key of the app's own user (the install made it)
                       ("user:<email>"); every call names its shop (X-iVendNext-Site).
CCO_PREFIX (default PP CCO; IVENDNEXT CCO for the library's app) · PORT (default 8080)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import http.client
import json
import os
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
import route  # noqa: E402
import shops  # noqa: E402

SUB = "route"           # the manifest's extension_subscriptions[].key; its secret is "<app>:sub:route"
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the order's own
APP_NAME = "Send to store"
NOT_SET_UP = (f"{APP_NAME} is not set up yet: no key from this shop has reached it. Ask your manager to check that the "
              "app's user has its key and, if the site could not reach the app, or a key was lost or changed, to press Connect again on the app.")
REFUSED = f"{APP_NAME} may not read or change this order. Ask your manager to check the app's user, its role and its API key."
CONNECT_AGAIN = " Then press Connect again on the app."    # many shops: a new key reaches the service only that way
NO_TERRITORY = "This order has no territory. Choose the customer's territory on the order, save it, and press Send to store again."
SUBMITTED = ("This order is already submitted, so it was not changed. To send it to another store, cancel and amend it, "
             "then press Send to store on the draft.")
GONE = "This order is no longer there. Reload the page."
CHANGED = "This order changed while it was being sent. Reload it and press Send to store again."
NOT_SAVED = "The shop would not save this order. Open it and press Save to see why, then press Send to store again."


def no_store(territory: str) -> str:
    return route._fit(f"No store serves {territory} or the territories above it. Ask your manager to set Serving store "
                      "on the territory, then press Send to store again.")


def not_taken(store: str) -> str:
    return route._fit(f"{store} cannot ship this order. Ask your manager to check that it is a store of this order's "
                      "company, not a group and not disabled, then press Send to store again.")


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code = code            # the shop's HTTP status, when it answered one
        self.kind = kind            # the shop's error type (exc_type), never its message


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _kind(e: urllib.error.HTTPError) -> str:
    """The shop's error type from its error body (``exc_type``): a name the service branches on, never shown."""
    try:
        kind = json.loads(e.read(64 * 1024) or b"{}").get("exc_type")
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        return ""
    return kind if isinstance(kind, str) and kind.isidentifier() else ""


class Tenant:
    """The service's only door into iVendNext: the record API, as the integration user (token key:secret)."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 3):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _call(self, method: str, path: str, body: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind = _kind(e)
            e.close()
            raise TenantError(f"{method} {path.split('/')[0]} -> HTTP {e.code}", e.code, kind) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {path.split('/')[0]} -> {type(e).__name__}") from None   # the outcome is unknown

    def _doc(self, method: str, doctype: str, name: str, body: dict | None = None) -> dict:
        try:
            data = self._call(method, f"{doctype}/{name}", body)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {doctype} -> an answer with no record") from None
        if not isinstance(data, dict):
            raise TenantError(f"{method} {doctype} -> an answer with no record")
        return data

    def order(self, name: str) -> dict:
        return self._doc("GET", "Sales Order", name)

    def territory(self, name: str) -> dict:
        return self._doc("GET", "Territory", name)

    def warehouse(self, name: str) -> dict:
        return self._doc("GET", "Warehouse", name)

    def write(self, name: str, body: dict) -> dict:
        return self._doc("PUT", "Sales Order", name, body)


def tenant_of(url: str, key: str) -> Tenant:
    """A shop's door from the key the shop's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str) -> dict:
    return {"message": {"title": APP_NAME, "body": body, "level": "warning"}}


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("CCO_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's field is not the sample's: every territory would read empty
            raise SystemExit("IVN_LIBRARY_APP is set but CCO_PREFIX is not (IVENDNEXT CCO for the App library's app)")
        route.use_prefix(prefix or "PP CCO")
        self.tenants = tenants
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secret, self.tenant = conf["PP_POINT_SECRET"], tenant
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []
        self._lock = threading.Lock()    # one shop: one press at a time

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

    def route_order(self, door, name: str) -> dict:
        """Read the order, find its store, check it, write once; a stale write is answered in words, never retried."""
        order = door.order(name)
        if order.get("docstatus") != 0:
            return _warning(SUBMITTED)
        territory = order.get("territory")
        if not territory:
            return _warning(NO_TERRITORY)
        try:
            store, named_by = route.store_for(territory, door.territory)
        except TenantError as e:
            if e.code == 404:                   # a territory up the tree is gone: no store can be named
                return _warning(no_store(territory))
            raise
        if not store:
            return _warning(no_store(territory))
        if route.routed(order, store):
            return route.already(store, named_by)
        try:            # the shop takes a group or another company's warehouse on a DRAFT and refuses it only at submit
            wh = door.warehouse(store)
        except TenantError as e:
            if e.code == 404:
                return _warning(not_taken(store))
            raise
        if not route.can_ship(wh, order):
            return _warning(not_taken(store))
        try:
            saved = door.write(name, route.plan(order, store))
        except TenantError as e:
            if e.kind == STALE:                 # someone saved it meanwhile: never write over their edit, nor retry;
                if route.routed(door.order(name), store):   # a second press (a double click, another copy) just routed it
                    return route.already(store, named_by)
                return _warning(CHANGED)
            if e.code == 417:                   # the order's own fault (a field the shop now requires): never its text
                return _warning(NOT_SAVED)
            raise
        return route.sent(order, store, named_by, saved)

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(route.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            name = route.order_of(body)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, _warning(NOT_SET_UP)
        try:
            if not self.app:
                with self._lock:        # one shop: one press at a time
                    return 200, self.route_order(door, name)
            return 200, self.route_order(door, name)
        except TenantError as e:
            if e.code in (401, 403):    # the shop refused the app's user: say so
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            if e.code == 404:
                return 200, _warning(GONE)
            # the shop tells the user "did not answer in time. Check the record before you try again": true, because
            # a write may have landed; a second press finds the order routed and writes nothing
            return 502, {"error": str(e)}

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

        def do_POST(self):
            t0, rid, code = time.monotonic(), (self.headers.get("X-iVendNext-Request-Id") or "-")[:40], 500
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if not 0 <= n <= route.BODY_MAX:
                    code = 413
                    return self._send(413, {"error": "too large"})
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n))
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            if self.path == "/test/received" and svc.test_modes and self.headers.get("X-PP-Admin") == svc.admin:
                return self._send(200, {"received": svc.received})
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the server's own access line carries the path; keep it off
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
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8147)), make_handler(svc))
    print(f"s35 send to store on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"field {route.FIELD}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
