"""S44 — *Lucky draw*: the partner's service behind the shop's two Desk buttons on a campaign (standard library only).

    POST /press/count   the shop's signed press of *Count entries* (``desk_action/1``)  →  200 {"message": …, "refresh": true}
    POST /press/draw    the shop's signed press of *Draw winners*                     →  200 {"message": …, "refresh": true}
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

For the pressed campaign it reads, with the app's own integration user's key (that user's rights, never the pressing
user's): the campaign, its days' submitted till sales (each sale's name, customer, customer group, total in the company's
currency, date, time and till), the returns made against them, every till's walk-in customer and, when the campaign lists
customer groups, the group tree. It counts each sale's entries (``draw.entries_of``). *Count entries* writes the counts on
the campaign; *Draw winners* draws once, after the campaign's last day, and writes the results, the draw's record and
*Drawn*. Every write carries the campaign's ``modified`` as read, so a press never writes over someone's edit, and a second
draw finds the campaign drawn (its status, or any part of a draw's record left on it) and writes nothing. A press reads for
at most ``BUDGET_S`` seconds; past it, it writes nothing and the shop says the press did not answer in time.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE SHOP (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_COUNT_SECRET and PP_DRAW_SECRET (handed back at install as
    pp_ldw:sub:count and pp_ldw:sub:draw), PP_ADMIN_TOKEN, PP_PORT (8150)
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_ldw), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
LDW_PREFIX (default PP LDW; IVENDNEXT LDW for the library's app) · PORT (default 8080)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import datetime
import http.client
import json
import os
import secrets as rng
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
import draw  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

ROUTES = {"/press/count": "count", "/press/draw": "draw"}   # the manifest's extension_subscriptions[].key for each
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
READ_S = 6                           # one read may take this long, within BUDGET_S; the shop waits 10 seconds at most,
                                     # and a hosted function's cold start (about 2.5 s, APPF run 9) comes first
SALE_FIELDS = ["name", "customer", "customer_group", "base_grand_total", "base_rounded_total", "posting_date",
               "posting_time", "pos_profile"]
BUDGET_S = 7.0                       # the whole press: past it, the press stops before it writes anything
NOT_SET_UP = ("Lucky draw is not set up yet. Ask your manager to choose its user on the app's feed and press "
              "Connect again.")
REFUSED = ("Lucky draw may not read the sales or write the campaign. Ask your manager to check the app's user, its role "
           "and its API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many shops: a new key reaches the service only that way
CHANGED = "The campaign was changed while this press read it. Open it again and press once more."
GONE = "This campaign was not found. Open it again from the list."


def too_soon(end: datetime.date) -> str:
    return f"The campaign runs until {end.isoformat()}. Draw after it ends, once every till has sent its sales."


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

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None,
              timeout: float | None = None) -> dict:
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout or self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind = _kind(e)
            e.close()
            raise TenantError(f"{method} {path.split('/')[0]} -> HTTP {e.code}", e.code, kind) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {path.split('/')[0]} -> {type(e).__name__}") from None   # the outcome is unknown

    def _data(self, method: str, path: str, body: dict | None = None, query: dict | None = None, kind=dict,
              timeout: float | None = None):
        try:
            data = self._call(method, path, body, query, timeout)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {path.split('/')[0]} -> an answer with no data") from None
        if not isinstance(data, kind):
            raise TenantError(f"{method} {path.split('/')[0]} -> an answer with no data")
        return data

    def doc(self, doctype: str, name: str) -> dict:
        return self._data("GET", f"{doctype}/{name}")

    def rows(self, doctype: str, fields: list, filters: list, timeout: float | None = None) -> list:
        return self._data("GET", doctype, query={"fields": fields, "filters": filters, "limit_page_length": 0},
                          kind=list, timeout=timeout)

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)


def tenant_of(url: str, key: str) -> Tenant:
    """A shop's door from the key it handed over on Connect again ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str) -> dict:
    return draw.message(body, "warning")


def _now_text(now: float) -> str:
    """The time as text, said in UTC: a date-time field would show it labelled with the site's own zone (the bench walk)."""
    return datetime.datetime.fromtimestamp(now, datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=None, randbelow=rng.randbelow,
                 clock=time.monotonic):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("LDW_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record type is not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but LDW_PREFIX is not (IVENDNEXT LDW for the App library's app)")
        draw.use_prefix(prefix or "PP LDW")
        self.tenants, self.now, self.randbelow, self.clock = tenants, now, randbelow, clock
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secrets = {"count": conf["PP_COUNT_SECRET"], "draw": conf["PP_DRAW_SECRET"]}
            self.tenant = tenant
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []
        self._lock = threading.Lock()    # one shop: one press at a time

    def caller(self, headers, sub: str) -> tuple[str, list[str], object | None]:
        """(the shop's name, the secrets its press may be signed with, its door: None until it handed over a user's key)."""
        if not self.app:
            return "-", [self.secrets[sub]], self.tenant
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{sub}")]
        users = sorted(k for k in (record or {}).get("secrets") or {}
                       if k.startswith("user:") and k != "user:Administrator")    # the site never sends it; nor do we use it
        door = self.tenants(record["url"], record["secrets"][users[0]]) if record and users else None
        return site or "", secrets, door

    def left(self, t0: float) -> float:
        """The time a read may still take; past the press's budget, nothing more is read and nothing is written."""
        rest = BUDGET_S - (self.clock() - t0)
        if rest <= 0:
            raise TenantError("the press ran out of time")
        return min(READ_S, rest)

    def entries(self, door, rules: draw.Rules, t0: float) -> list:
        """The campaign's entries, read from the shop as they stand now."""
        sale_filters = [["docstatus", "=", 1], ["is_return", "=", 0], ["company", "=", rules.company],
                        ["posting_date", "between", [rules.start.isoformat(), rules.end.isoformat()]]]
        if rules.tills:
            sale_filters.append(["pos_profile", "in", rules.tills])
        sales = door.rows("POS Invoice", SALE_FIELDS, sale_filters, timeout=self.left(t0))
        returns = door.rows("POS Invoice", ["return_against", "base_grand_total", "base_rounded_total"],
                            [["docstatus", "=", 1], ["is_return", "=", 1], ["company", "=", rules.company],
                             ["posting_date", ">=", rules.start.isoformat()]], timeout=self.left(t0))
        walk_ins = {r.get("customer") for r in door.rows("POS Profile", ["name", "customer"], [], timeout=self.left(t0))
                    if isinstance(r, dict) and r.get("customer")}
        groups = None
        if rules.groups:
            groups = draw.groups_under(door.rows("Customer Group", ["name", "lft", "rgt"], [], timeout=self.left(t0)),
                                       rules.groups)
        return draw.entries_of(sales, returns, walk_ins, rules, groups)

    def run(self, door, sub: str, name: str, user: str) -> dict:
        t0 = self.clock()
        now = self.now if self.now is not None else time.time()
        try:
            c = door.doc(draw.CAMPAIGN, name)
        except TenantError as e:
            if e.code == 404:
                return _warning(GONE)
            raise
        if sub == "draw" and draw.already_drawn(c):
            return draw.already_answer(c.get("drawn_on"), c.get("drawn_by"))
        rules = draw.rules_of(c)
        if isinstance(rules, str):
            return _warning(rules)
        if sub == "draw" and draw.today_at(c.get("hours_from_utc"), now) <= rules.end:
            return _warning(too_soon(rules.end))
        entries = self.entries(door, rules, t0)
        self.left(t0)                   # out of time after the reads: nothing is written
        sales, customers, n = len(entries), len({e[1] for e in entries}), sum(e[2] for e in entries)
        mark = draw.fingerprint(entries)
        body = {"counted_on": _now_text(now), "sales_counted": sales, "customers_counted": customers,
                "entries_counted": n, "count_fingerprint": mark, "modified": c.get("modified")}
        if sub == "count":              # a count after the draw writes the counts only: the draw's record stands
            answer = draw.count_answer(entries)
        else:
            if not n:
                return draw.count_answer(entries)       # nothing to draw from: nothing written, the button stays
            places = draw.draw(entries, rules.winners + rules.reserves, self.randbelow)
            results = draw.results_of(places, rules.winners)
            body.update(status=draw.DRAWN, drawn_on=_now_text(now), drawn_by=user, draw_entries=n,
                        draw_fingerprint=mark, drawn_numbers=", ".join(str(p["entry_no"]) for p in results),
                        results=results)
            answer = draw.draw_answer(results, rules.winners, rules.reserves, entries)
        try:
            door.update(draw.CAMPAIGN, name, body)
        except TenantError as e:
            if e.kind == STALE:                 # someone saved the campaign, or another press drew it, meanwhile
                return _warning(CHANGED)
            raise
        return answer

    def press(self, sub: str, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.caller(headers, sub)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(draw.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            name, user = draw.campaign_of(body)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, _warning(NOT_SET_UP)
        try:
            if not self.app:
                with self._lock:        # one shop: one press at a time
                    return 200, self.run(door, sub, name, user)
            return 200, self.run(door, sub, name, user)
        except TenantError as e:
            if e.code in (401, 403):    # the shop refused the app's user: say so
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app else ""))
            # the shop tells the user "did not answer in time. Check the record before you try again": nothing was
            # written unless the one update landed, and a second draw then finds Drawn
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > draw.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        if path in ROUTES:
            return self.press(ROUTES[path], headers, raw)
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
                if not 0 <= n <= draw.BODY_MAX:
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
    elif all(conf.get(k) for k in ("PP_BASE", "PP_KEY", "PP_SECRET", "PP_COUNT_SECRET", "PP_DRAW_SECRET")):
        svc = Service(conf, Tenant(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    else:
        raise SystemExit("set PP_BASE, PP_KEY, PP_SECRET, PP_COUNT_SECRET and PP_DRAW_SECRET (one shop), or "
                         "IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a press")
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8150)), make_handler(svc))
    print(f"s44 lucky draw on :{srv.server_port} ({'many shops, ' + svc.app if svc.app else 'one shop'}, "
          f"prefix {draw.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
