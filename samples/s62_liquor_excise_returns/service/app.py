"""S62 — *Liquor excise returns*: the partner's service behind the retailer's Desk button on a draft return (standard
library only).

    POST /exr/work     the retailer's signed press of *Work out the return* (``desk_action/1``)  →  200 {"message": …, "refresh": true}
    GET  /health       200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

For the pressed return it reads, with the app's own integration user's key (that user's rights, never the pressing
user's): the return (company, store, period, unit), the lock rule's state (no lock, no figures), the duty classes and their return codes, the items that have a duty
class (millilitres and strength), and from the store's stock ledger, never a row at a time: each item's last ledger time
before the period and at its end (``max(posting_datetime)`` per item), the rows at those times (their balance), the
period's totals per item and voucher type in and out, the Stock Entries' net movement per item and entry, and those
entries' purpose (``exr.work_out``), the time and name lists ``CHUNK_BYTES`` of them a read. It writes the return's lines, its summary and who worked it out, carrying the
return's ``modified`` as read, so a press never writes over someone's edit. A press reads for at most ``BUDGET_S``
seconds; past it, it writes nothing and the site says the press did not answer in time.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE RETAILER (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_WORK_SECRET (handed back at install as pp_exr:sub:work),
    PP_ADMIN_TOKEN, PP_PORT (8162)
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_exr), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
EXR_PREFIX (default PP EXR; IVENDNEXT EXR for the library's app) · PORT (default 8080)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

import datetime
import hmac
import http.client
import json
import os
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
import exr  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

ROUTES = {"/exr/work": "work"}       # the manifest's extension_subscriptions[].key for each
STALE = "TimestampMismatchError"     # the site's refusal of a write whose ``modified`` is not the row's own
RIGHTS_KINDS = ("PermissionError",)  # a 417 that is a rights problem; any other 417 (a value the site refused) takes the
                                     # site's own did-not-answer words
LEDGER = "Stock Ledger Entry"
CHUNK_BYTES = 2000                   # the values' bytes a read, as sent: the request line stays under 4 KB (S23's
                                     # PRICE_CHUNK); 200 ledger times a read was 8.4 KB (the Tier-S review)
AT_ONCE = 4                          # chunk reads run this many at a time: about 50 ledger times a read, so a store of
                                     # 2,000 liquor items needs about 40 reads, ten rounds of four
READ_S = 6                           # one read may take this long, within BUDGET_S; the site waits 10 seconds at most,
                                     # and a hosted function's cold start (about 2.5 s, APPF run 9) comes first
BUDGET_S = 7.0                       # the whole press: past it, the press stops before it writes anything
NOT_SET_UP = ("Liquor excise returns is not set up yet: no key from this site has reached it. Ask your manager to check "
              "that the app's user has its key and, if the site could not reach the app, or a key was lost or changed, "
              "to press Connect again on the app.")
REFUSED = ("Liquor excise returns may not read the stock ledger, stock entries, items or the lock rule (Retail Save Rule), "
           "or write the return. Ask your "
           "manager to check the app's user, its role and its rights (the app's set-up names them).")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way
CHANGED = "The return was changed while this press read it. Open it again and press once more."
GONE = "This return was not found. Open it again from the list."
NOT_DRAFT = "Only a draft return can be worked out. This one is filed or dropped: make a new return for a correction."
NO_STORE = "Choose the company, the store and the period first, then save the return."
EMPTY_STORE = ("This store has no stock movements up to the end of the period, so there is nothing to return. Check that "
               "the store is a warehouse that holds stock (not a group of warehouses), and that the app's user has no User "
               "Permission that limits what it reads. Nothing was written.")
BAD_UNIT = "Choose the unit, Litres or US gallons, then save the return."
LOCK_OFF = ("Switch on the rule {} in Retail Save Rule, set to refuse, first: a filed return is kept as filed only while "
            "it is. "
            "Nothing was written.")


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code = code            # the site's HTTP status, when it answered one
        self.kind = kind            # the site's error type (exc_type), never its message


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _kind(e: urllib.error.HTTPError) -> str:
    """The site's error type from its error body (``exc_type``): a name the service branches on, never shown."""
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

    def doc(self, doctype: str, name: str, timeout: float | None = None) -> dict:
        return self._data("GET", f"{doctype}/{name}", timeout=timeout)

    def rows(self, doctype: str, fields: list, filters: list, group_by: str | None = None,
             timeout: float | None = None) -> list:
        """A list read; with ``group_by``, the site adds up (``sum(…)``, ``max(…)`` in ``fields``) and sends one row a group."""
        q = {"fields": fields, "filters": filters, "limit_page_length": 0}
        if group_by:
            q["group_by"] = group_by
        return [r for r in self._data("GET", doctype, query=q, kind=list, timeout=timeout) if isinstance(r, dict)]

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)


def chunks(values: list[str]):
    """The values in reads whose ``in`` list, as the query string carries it, stays within CHUNK_BYTES bytes."""
    chunk, size = [], 0
    for v in values:
        n = len(urllib.parse.quote_plus(json.dumps(v))) + 4          # the value and its ", " as urlencode sends them
        if chunk and size + n > CHUNK_BYTES:
            yield chunk
            chunk, size = [], 0
        chunk.append(v)
        size += n
    if chunk:
        yield chunk


def tenant_of(url: str, key: str) -> Tenant:
    """A retailer's door from the key the retailer's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str, refresh: bool = False) -> dict:
    return exr.message(body, "warning", refresh)


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, clock=time.monotonic, now=None):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("EXR_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but EXR_PREFIX is not (IVENDNEXT EXR for the App library's app)")
        exr.use_prefix(prefix or "PP EXR")
        self.tenants, self.clock = tenants, clock
        self.now = now or (lambda: datetime.datetime.now(datetime.timezone.utc))
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            self.secrets = {"work": conf["PP_WORK_SECRET"]}
            self.tenant = tenant
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []
        self._lock = threading.Lock()    # one retailer: one press at a time

    def caller(self, headers, sub: str) -> tuple[str, list[str], object | None]:
        """(the site's name, the secrets its press may be signed with, its door: None until it handed over a user's key)."""
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

    def _in(self, door, doctype, fields, field, values, t0, filters=()) -> list:
        """``rows`` for a long list of values, ``CHUNK_BYTES`` of them a read, ``AT_ONCE`` reads at a time."""
        reads = [list(filters) + [[field, "in", c]] for c in chunks(sorted(set(values)))]
        if len(reads) < 2:
            return [r for f in reads for r in door.rows(doctype, fields, f, timeout=self.left(t0))]
        with ThreadPoolExecutor(max_workers=AT_ONCE) as pool:     # a read's failure is raised here, as one after another
            parts = list(pool.map(lambda f: door.rows(doctype, fields, f, timeout=self.left(t0)), reads))
        return [r for part in parts for r in part]

    def balances(self, door, store: str, start: str, end: str, items: dict, t0: float) -> tuple[dict, dict, int]:
        """(each item's balance in ``store`` at ``start`` and at ``end`` (each exclusive): its last ledger row's
        ``qty_after_transaction``, the number of items of any kind the store's ledger holds before ``end``). The rows at
        both ends' last times are read in one pass: an item that did not move in the period has the same time at both."""
        base = [["warehouse", "=", store], ["is_cancelled", "=", 0]]
        ends = []
        for before in (start, end):
            every = door.rows(LEDGER, ["item_code", "max(posting_datetime) as last_at"],
                              base + [["posting_datetime", "<", before]], group_by="item_code", timeout=self.left(t0))
            ends.append([{"item_code": r["item_code"], "at": r["last_at"]} for r in every
                         if r.get("item_code") in items and r.get("last_at")])
        times = {str(a["at"]) for side in ends for a in side}
        rows = self._in(door, LEDGER, ["name", "item_code", "posting_datetime", "creation", "qty_after_transaction"],
                        "posting_datetime", times, t0, filters=base) if times else []
        return exr.last_balances(ends[0], rows), exr.last_balances(ends[1], rows), len(every)

    def work(self, door, r: dict, user: str, t0: float) -> dict:
        bounds = exr.period(r.get("from_date"), r.get("to_date"))
        if isinstance(bounds, str):
            return _warning(bounds)
        start, end = bounds
        store = r["store"]
        codes = {c["name"]: c.get("return_code") or "" for c in door.rows(exr.CLASS, ["name", "return_code"], [],
                                                                           timeout=self.left(t0)) if c.get("name")}
        items = {i["name"]: exr.item_of(i) for i in door.rows(
            "Item", ["name", "item_name", exr.FIELD + "class", exr.FIELD + "ml", exr.FIELD + "abv"],
            [[exr.FIELD + "class", "is", "set"]], timeout=self.left(t0)) if i.get("name")}
        opening, closing, held = self.balances(door, store, start, end, items, t0) if items else ({}, {}, 0)
        if items and not held:           # a group of warehouses, or a user permission: never an empty return to file
            return _warning(EMPTY_STORE)
        span = [["warehouse", "=", store], ["is_cancelled", "=", 0], ["posting_datetime", ">=", start],
                ["posting_datetime", "<", end]]
        moves, entries = [], []
        if items:
            for sign in (">", "<"):
                moves += door.rows(LEDGER, ["item_code", "voucher_type", "sum(actual_qty) as qty"],
                                   span + [["voucher_type", "not in", list(exr.SKIPPED)], ["actual_qty", sign, 0]],
                                   group_by="item_code, voucher_type", timeout=self.left(t0))
            entries = door.rows(LEDGER, ["item_code", "voucher_no", "sum(actual_qty) as qty"],
                                span + [["voucher_type", "=", "Stock Entry"]], group_by="item_code, voucher_no",
                                timeout=self.left(t0))
            entries = [e for e in entries if e.get("item_code") in items]
        purposes = {e["name"]: e.get("purpose") for e in self._in(
            door, "Stock Entry", ["name", "purpose"], "name", {e.get("voucher_no") for e in entries if e.get("voucher_no")},
            t0)} if entries else {}
        lines, missing, counted, counts = exr.work_out(items, opening, closing, moves, entries, purposes, r["unit"], codes)
        words = exr.summary_of(lines, missing, counted, r["unit"], counts)
        self.left(t0)                   # out of time after the reads: nothing is written
        door.update(exr.RETURN, r["name"], {"lines": exr.as_written(lines), "summary": words, "worked_out_by": user,
                                            "worked_out_at": self.now().strftime("%Y-%m-%d %H:%M UTC"),
                                            "modified": r.get("modified")})
        return exr.message(words, "success" if lines else "info", refresh=True)

    def run(self, door, sub: str, name: str, user: str) -> dict:
        t0 = self.clock()
        try:
            r = door.doc(exr.RETURN, name, timeout=self.left(t0))
        except TenantError as e:
            if e.code == 404:
                return _warning(GONE)
            raise
        if (r.get("workflow_state") or exr.DRAFT) != exr.DRAFT:
            return _warning(NOT_DRAFT, refresh=True)
        if not r.get("store") or not r.get("company"):
            return _warning(NO_STORE)
        if r.get("unit") not in exr.UNITS:
            return _warning(BAD_UNIT)
        lock = door.rows("Retail Save Rule", ["name", "enabled", "mode"], [["rule_name", "=", exr.LOCK_RULE]],
                         timeout=self.left(t0))
        if not lock or not lock[0].get("enabled") or lock[0].get("mode") != "refuse":   # S61's Pay guard
            return _warning(LOCK_OFF.format(exr.LOCK_RULE))
        try:
            return self.work(door, r, user, t0)
        except TenantError as e:
            if e.kind == STALE:                 # someone saved the return, or another press wrote it, meanwhile
                return _warning(CHANGED)
            raise

    def press(self, sub: str, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.caller(headers, sub)
        except Exception:               # noqa: BLE001 — the retailers store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(exr.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            name, user = exr.return_of(body)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, _warning(NOT_SET_UP)
        try:
            if not self.app:
                with self._lock:        # one retailer: one press at a time
                    return 200, self.run(door, sub, name, user)
            return 200, self.run(door, sub, name, user)
        except TenantError as e:
            if e.code in (401, 403) or (e.code == 417 and e.kind in RIGHTS_KINDS):   # the site refused the app's user
                return 200, _warning(REFUSED + (CONNECT_AGAIN if self.app and e.code == 401 else ""))
            # the site tells the user "did not answer in time. Check the record before you try again": nothing was
            # written unless the one update landed, and the return then shows it
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > exr.BODY_MAX:
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
                if not 0 <= n <= exr.BODY_MAX:
                    code = 413
                    return self._send(413, {"error": "too large"})
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n))
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            if self.path == "/test/received" and svc.test_modes and hmac.compare_digest(
                    (self.headers.get("X-PP-Admin") or "").encode(), svc.admin.encode()):
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
    elif all(conf.get(k) for k in ("PP_BASE", "PP_KEY", "PP_SECRET", "PP_WORK_SECRET")):
        svc = Service(conf, Tenant(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    else:
        raise SystemExit("set PP_BASE, PP_KEY, PP_SECRET and PP_WORK_SECRET (one retailer), or IVN_LIBRARY_APP with a "
                         "store (many retailers): the app does not start without a way to check a press")
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8162)), make_handler(svc))
    print(f"s62 liquor excise returns on :{srv.server_port} ({'many retailers, ' + svc.app if svc.app else 'one retailer'}, "
          f"prefix {exr.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
