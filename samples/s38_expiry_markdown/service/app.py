"""S38 — *Mark down*: the partner's service behind the shop's Desk button on the Batch list (standard library only).

    POST /press/markdown   the shop's signed press (``desk_action/1``)  →  200 {"message": …, "refresh": true}
    GET  /health           200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

For the ticked lots it reads, with the app's own integration user's key (that user's rights, never the pressing user's),
the shop's settings (the price list, the hours from UTC), the lots, their items, the item group tree with its markdown
steps, the list's currency and those items' prices on the list. Then, lot by lot, it writes each lot's own price (the
item's price less the step's percent, valid until the lot's expiry date, noted as the app's own), changes it when the lot
reached its last step, and removes it when the lot is past its date, out of stock or out of every step. A price the shop
typed for a lot is never changed. Then it removes up to ``SWEEP`` of its own prices whose date has passed, anywhere, and
answers. A press repeated (a retry, a second click, two copies of the function) finds the prices already right and
writes nothing; an update carries the row's ``modified`` as read, so it never writes over someone's edit. A press stops
starting new lots after ``BUDGET_S`` seconds and says how many are left: the shop waits at most 10 seconds.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_POINT_SECRET (handed back at install as pp_exm:sub:markdown),
    PP_ADMIN_TOKEN, PP_PORT (8150)
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_exm), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
EXM_PREFIX (default PP EXM; IVENDNEXT EXM for the library's app) · PORT (default 8080)

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
import markdown  # noqa: E402
import shops  # noqa: E402

SUB = "markdown"        # the manifest's extension_subscriptions[].key; its secret is "<app>:sub:markdown"
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
BUDGET_S = 5.0          # no new lot is started after this: the shop waits 10 seconds at most, and a hosted function's
                        # cold start (about 2.5 s, APPF run 9) comes before this clock starts
SWEEP = 20              # expired prices of the app's own removed per press, at most
APP_NAME = "Mark down"
NOT_SET_UP = (f"{APP_NAME} is not set up yet: no key from this shop has reached it. Ask your manager to check that the "
              "app's user has its key and, if the site could not reach the app, or a key was lost or changed, to press Connect again on the app.")
REFUSED = f"{APP_NAME} may not read or change prices. Ask your manager to check the app's user, its role and its API key."
CONNECT_AGAIN = " Then press Connect again on the app."    # many shops: a new key reaches the service only that way
NO_SETTINGS = ("Mark down has no price list yet. Ask your manager to open the settings record Default and choose the "
               "price list your tills sell from.")


def bad_list(price_list: str) -> str:
    return markdown._fit(f"Mark down cannot use the price list {price_list}: it is not a selling price list that is "
                         "switched on. Ask your manager to choose another in the settings record Default.")


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

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None) -> dict:
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
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

    def _data(self, method: str, path: str, body: dict | None = None, query: dict | None = None, kind=dict):
        try:
            data = self._call(method, path, body, query)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {path.split('/')[0]} -> an answer with no data") from None
        if not isinstance(data, kind):
            raise TenantError(f"{method} {path.split('/')[0]} -> an answer with no data")
        return data

    def doc(self, doctype: str, name: str) -> dict:
        return self._data("GET", f"{doctype}/{name}")

    def rows(self, doctype: str, fields: list, filters: list) -> list:
        return self._data("GET", doctype, query={"fields": fields, "filters": filters, "limit_page_length": 0}, kind=list)

    def create(self, doctype: str, body: dict) -> dict:
        return self._data("POST", doctype, body)

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)

    def delete(self, doctype: str, name: str) -> None:
        self._call("DELETE", f"{doctype}/{name}")


def tenant_of(url: str, key: str) -> Tenant:
    """A shop's door from the key the shop's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str) -> dict:
    return {"message": {"title": APP_NAME, "body": body, "level": "warning"}}


PRICE_FIELDS = ["name", "item_code", "uom", "packing_unit", "batch_no", "customer", "supplier", "price_list_rate",
                "valid_from", "valid_upto", "note", "modified"]


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, clock=time.monotonic, now=None):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("EXM_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's fields are not the sample's: every group would read empty
            raise SystemExit("IVN_LIBRARY_APP is set but EXM_PREFIX is not (IVENDNEXT EXM for the App library's app)")
        markdown.use_prefix(prefix or "PP EXM")
        self.settings = f"{markdown.PREFIX} Settings"
        self.tenants, self.clock, self.now = tenants, clock, now
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

    def write(self, door, w) -> str:
        """One write; ``""`` when it landed, else the outcome that names why not (never the shop's own text)."""
        try:
            if w[0] == "create":
                door.create("Item Price", w[1])
            elif w[0] == "update":
                door.update("Item Price", w[1]["name"], w[2])
            else:
                door.delete("Item Price", w[1]["name"])
        except TenantError as e:
            if e.kind == STALE or (w[0] == "delete" and e.code == 404):   # someone changed it, or it is already gone
                return "changed" if e.kind == STALE else ""
            if e.code in (409, 417):        # the shop's own refusal (a duplicate written by a second press, a date)
                return "changed" if e.kind in ("DuplicateEntryError", "ItemPriceDuplicateItem") else "refused"
            raise
        return ""

    def mark_down(self, door, lots: list[str]) -> dict:
        t0 = self.clock()
        try:
            settings = door.doc(self.settings, "Default")
        except TenantError as e:
            if e.code == 404:
                return _warning(NO_SETTINGS)
            raise
        price_list = settings.get("price_list")
        if not price_list:
            return _warning(NO_SETTINGS)
        try:
            pl = door.doc("Price List", price_list)
        except TenantError as e:
            if e.code == 404:
                return _warning(bad_list(price_list))
            raise
        if not pl.get("selling") or not pl.get("enabled"):
            return _warning(bad_list(price_list))
        try:            # the currency's own digits: never guessed, a price rounded to the wrong grain is a wrong price
            exponent = markdown.exponent_of(door.doc("Currency", pl.get("currency") or "-").get("number_format"))
        except TenantError as e:
            if e.code == 404:
                return _warning(bad_list(price_list))
            raise
        hours = settings.get("hours_from_utc")
        today = markdown.today_at(hours if isinstance(hours, (int, float)) else 0, self.now)
        got = {r["name"]: r for r in door.rows("Batch", ["name", "item", "expiry_date", "batch_qty", "disabled"],
                                               [["name", "in", lots]]) if isinstance(r, dict) and r.get("name")}
        items = sorted({r.get("item") for r in got.values() if r.get("item")})
        item_rows = {r["name"]: r for r in door.rows("Item", ["name", "item_group"], [["name", "in", items]])
                     if isinstance(r, dict) and r.get("name")} if items else {}
        groups = markdown.groups_of(door.rows("Item Group", ["name", "lft", "rgt", *markdown.DAYS, *markdown.PCT], []))
        prices = door.rows("Item Price", PRICE_FIELDS, [["price_list", "=", price_list], ["item_code", "in", items]]) \
            if items else []
        outcomes, done = {}, 0
        for name in lots:
            if done and self.clock() - t0 > BUDGET_S:
                break
            lot = got.get(name) or {"name": name}
            outcome, writes = markdown.plan(lot, item_rows.get(lot.get("item")), prices, groups, today, price_list,
                                            exponent)
            for w in writes:
                why = self.write(door, w)
                if why:
                    outcome = why
                    break
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            done += 1
        swept = 0
        if self.clock() - t0 <= BUDGET_S:
            old = door.rows("Item Price", ["name", "note", "valid_upto"],
                            [["note", "like", markdown.PREFIX + ": %"], ["valid_upto", "<", today.isoformat()]])
            for r in [r for r in old if isinstance(r, dict) and markdown.own(r)][:SWEEP]:
                if self.clock() - t0 > BUDGET_S:
                    break
                if not self.write(door, ("delete", r)):
                    swept += 1
        return markdown.answer(outcomes, done, len(lots), swept)

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(markdown.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            lots = markdown.lots_of(body)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, _warning(NOT_SET_UP)
        try:
            if not self.app:
                with self._lock:        # one shop: one press at a time
                    return 200, self.mark_down(door, lots)
            return 200, self.mark_down(door, lots)
        except TenantError as e:
            if e.code in (401, 403):    # the shop refused the app's user: say so
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            # the shop tells the user "did not answer in time. Check the record before you try again": true, because
            # some prices may have been written; a second press finds them right and writes nothing
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > markdown.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path == "/press/markdown":
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
                if not 0 <= n <= markdown.BODY_MAX:
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
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8150)), make_handler(svc))
    print(f"s38 mark down on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"prefix {markdown.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
