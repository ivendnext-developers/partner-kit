"""S61 — *Consignment payouts*: the partner's service behind the retailer's two Desk buttons on a draft payout (standard
library only).

    POST /csg/work     the retailer's signed press of *Work out the payout* (``desk_action/1``)  →  200 {"message": …, "refresh": true}
    POST /csg/pay      the retailer's signed press of *Pay this payout*                          →  200 {"message": …, "refresh": true}
    GET  /health       200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

For the pressed payout it reads, with the app's own integration user's key (that user's rights, never the pressing
user's): the payout, its consignor's share and *Consigned since*, the consignor's payouts (one draft a consignor), the consignor's items
(each one's own share), every till sale line and Desk invoice line of those items, those sales' headers, the lines other
payouts already hold, and the lines of the consignor's paid payouts with their sales' state (``consign.work_out``).
*Work out the payout* writes the payout's lines, its totals and a summary. *Pay this payout* writes nothing but the
payout's step: it reads the same again and the payout lock's state, checks the payout's lines are exactly what is owed now
and on no other payout (``consign.check_to_pay``), and only then moves the payout to Paid, which only the app's own role
may do (the workflow's transition). Every write carries the payout's ``modified`` as read, so a press never writes over
someone's edit. A press reads for at most ``BUDGET_S`` seconds; past it, it writes nothing and the site says the press
did not answer in time.

Test-only routes, ON ONLY when the process starts with ``PP_TEST_MODES=1`` in its environment and the caller sends
the ``X-PP-Admin`` token: ``GET /test/received`` returns the last presses as received. A partner's copy deletes them.

ONE RETAILER (an env file):
    PP_BASE, PP_KEY, PP_SECRET (the integration user), PP_WORK_SECRET and PP_PAY_SECRET (handed back at install as
    pp_csg:sub:work and pp_csg:sub:pay), PP_ADMIN_TOKEN, PP_PORT (8161)
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_csg), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
CSG_PREFIX (default PP CSG; IVENDNEXT CSG for the library's app) · PORT (default 8080)

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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import consign  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

ROUTES = {"/csg/work": "work", "/csg/pay": "pay"}   # the manifest's extension_subscriptions[].key for each
STALE = "TimestampMismatchError"     # the site's refusal of a write whose ``modified`` is not the row's own
RIGHTS_KINDS = ("PermissionError", "WorkflowPermissionError")   # a 417 that is a rights problem;
                                     # any other 417 (a value the site refused) takes the site's own did-not-answer words
CHUNK = 200                          # names a read: fewer reads in the press's time, the address still short
READ_S = 6                           # one read may take this long, within BUDGET_S; the site waits 10 seconds at most,
                                     # and a hosted function's cold start (about 2.5 s, APPF run 9) comes first
BUDGET_S = 7.0                       # the whole press: past it, the press stops before it writes anything
LINE_READ = ["name", "parent", "item_code", "item_name", "qty", "base_net_amount"]
HEAD_READ = {"POS Invoice": ["name", "docstatus", "company", "posting_date", "is_return"],
             "Sales Invoice": ["name", "docstatus", "company", "posting_date", "is_return", "is_consolidated"]}
HOLD_READ = ["parent", "sale_row", "sale_line"]
PAID_READ = ["parent", "sale_type", "sale", "sale_row", "sale_line", "kind", "posting_date", "item_code", "item_name",
             "sale_amount", "share", "payout"]
NOT_SET_UP = ("Consignment payouts is not set up yet: no key from this site has reached it. Ask your manager to check "
              "that the app's user has its key and, if the site could not reach the app, or a key was lost or changed, "
              "to press Connect again on the app.")
REFUSED = ("Consignment payouts may not read the sales and items or write the payout. Ask your manager to check the "
           "app's user, its role and its rights (the app's set-up names them).")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way
CHANGED = "The payout was changed while this press read it. Open it again and press once more."
GONE = "This payout was not found. Open it again from the list."
NOT_DRAFT = "Only a draft payout can be worked out. This one is already paid or cancelled."
NO_CONSIGNOR = "Choose the consignor and the company first, then save the payout."
OTHER_DRAFT = ("Payout {} for this consignor is still a draft. Pay it, work it out again, or drop it (Actions, Drop) "
               "first: a consignor has one draft payout at a time.")


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

    def rows(self, doctype: str, fields: list, filters: list, parent: str | None = None,
             timeout: float | None = None) -> list:
        """A list read; a table's rows are read through their record type (``parent``), with its read check."""
        q = {"fields": fields, "filters": filters, "limit_page_length": 0}
        if parent:
            q["parent"] = parent
        return [r for r in self._data("GET", doctype, query=q, kind=list, timeout=timeout) if isinstance(r, dict)]

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)


def tenant_of(url: str, key: str) -> Tenant:
    """A retailer's door from the key the retailer's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _warning(body: str, refresh: bool = False) -> dict:
    return consign.message(body, "warning", refresh)


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, clock=time.monotonic):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("CSG_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but CSG_PREFIX is not (IVENDNEXT CSG for the App library's app)")
        consign.use_prefix(prefix or "PP CSG")
        self.tenants, self.clock = tenants, clock
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            self.secrets = {"work": conf["PP_WORK_SECRET"], "pay": conf["PP_PAY_SECRET"]}
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

    def _in(self, door, doctype, fields, field, names, t0, filters=(), parent=None) -> list:
        """``rows`` for a long list of names, ``CHUNK`` a read."""
        names, out = sorted(set(names)), []
        for i in range(0, len(names), CHUNK):
            out += door.rows(doctype, fields, list(filters) + [[field, "in", names[i:i + CHUNK]]], parent=parent,
                             timeout=self.left(t0))
        return out

    def owed(self, door, p: dict, t0: float) -> tuple[list[dict], str, dict]:
        """(every line the payout's consignor is owed now, the words when none can be worked out, the holds)."""
        found = door.rows(consign.CONSIGNOR, ["name", "share", "since"], [["name", "=", p.get("consignor")]],
                          timeout=self.left(t0))
        if not found:
            return [], NO_CONSIGNOR, {}
        mine = door.rows(consign.PAYOUT, ["name", "company", "workflow_state"], [["consignor", "=", p["consignor"]]],
                         timeout=self.left(t0))
        drafts = sorted(r["name"] for r in mine if r.get("name") != p.get("name")
                        and (r.get("workflow_state") or consign.DRAFT) == consign.DRAFT)
        if drafts:                      # one draft a consignor: a second would hide the first one's lines from it
            return [], OTHER_DRAFT.format(drafts[0]), {}
        paid = [r["name"] for r in mine if r.get("workflow_state") == consign.PAID and r.get("company") == p.get("company")]
        items = {r["name"]: {"item_name": r.get("item_name"), "share": r.get(consign.FIELD + "share")}
                 for r in door.rows("Item", ["name", "item_name", consign.FIELD + "share"],
                                    [[consign.FIELD + "consignor", "=", p["consignor"]]], timeout=self.left(t0))
                 if r.get("name")}
        settled = self._in(door, consign.LINE, PAID_READ, "parent", paid, t0, parent=consign.PAYOUT) if paid else []
        lines, heads = [], {}
        for typ in consign.SALE_TYPES:
            got = self._in(door, typ + " Item", LINE_READ, "item_code", items, t0, filters=[["docstatus", "!=", 0]],
                           parent=typ) if items else []
            lines += [dict(r, sale_type=typ) for r in got]
            parents = {r.get("parent") for r in got if r.get("parent")}
            parents |= {r.get("sale") for r in settled if r.get("sale_type") == typ and r.get("sale")}
            for h in self._in(door, typ, HEAD_READ[typ], "name", parents, t0, filters=[["docstatus", "!=", 0]]) \
                    if parents else []:
                heads[(typ, h.get("name"))] = h
        keys = [str(r["name"]) for r in lines if r.get("name")]
        held = self._in(door, consign.LINE, HOLD_READ, "sale_row", keys, t0, parent=consign.PAYOUT) if keys else []
        states = {r.get("name"): r.get("workflow_state") or consign.DRAFT
                  for r in (self._in(door, consign.PAYOUT, ["name", "workflow_state"], "name",
                                     {r.get("parent") for r in held if r.get("parent")}, t0) if held else [])}
        holds = consign.holds_of(held, states, p.get("name"))
        up_to = consign.date_of(p.get("up_to")) or datetime.date.today()
        rows, why = consign.work_out(found[0].get("share"), items, lines, heads, holds, settled, p.get("company"), up_to,
                                     consign.date_of(found[0].get("since")))
        return rows, why, holds

    def work(self, door, p: dict, user: str, t0: float) -> dict:
        rows, why, _ = self.owed(door, p, t0)
        if why:
            return _warning(why)
        n = consign.MOST_LINES
        while n < len(rows) and consign.totals(rows[:n])[1] < 0:   # a kept part below 0 would stick: take the next
            n += 1
        kept, left = rows[:n], len(rows) - n
        sales, part = consign.totals(kept)
        words = consign.summary_of(kept, left, p.get("currency") or "")
        self.left(t0)                   # out of time after the reads: nothing is written
        door.update(consign.PAYOUT, p["name"], {"lines": consign.as_written(kept), "sales_total": float(sales),
                                                "payout_total": float(part), "summary": words, "worked_out_by": user,
                                                "modified": p.get("modified")})
        return consign.message(words, "success" if kept else "info", refresh=True)

    def pay(self, door, p: dict, user: str, t0: float) -> dict:
        rows, why, holds = self.owed(door, p, t0)
        if why:
            return _warning(why)
        lock = door.rows("Retail Save Rule", ["name", "enabled", "mode"], [["rule_name", "=", consign.LOCK_RULE]],
                         timeout=self.left(t0))
        refused = consign.check_to_pay(p, rows, holds, lock[0] if lock else None)
        if refused:
            return _warning(refused)
        self.left(t0)
        door.update(consign.PAYOUT, p["name"], {"workflow_state": consign.PAID, "paid_by": user,
                                                "modified": p.get("modified")})
        return consign.paid_answer(p.get("payout_total") or 0, p.get("currency") or "")

    def run(self, door, sub: str, name: str, user: str) -> dict:
        t0 = self.clock()
        try:
            p = door.doc(consign.PAYOUT, name, timeout=self.left(t0))
        except TenantError as e:
            if e.code == 404:
                return _warning(GONE)
            raise
        if (p.get("workflow_state") or consign.DRAFT) != consign.DRAFT:
            return _warning(NOT_DRAFT, refresh=True)
        if not p.get("consignor") or not p.get("company"):
            return _warning(NO_CONSIGNOR)
        try:
            return (self.work if sub == "work" else self.pay)(door, p, user, t0)
        except TenantError as e:
            if e.kind == STALE:                 # someone saved the payout, or another press wrote it, meanwhile
                return _warning(CHANGED)
            raise

    def press(self, sub: str, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.caller(headers, sub)
        except Exception:               # noqa: BLE001 — the retailers store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(consign.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            name, user = consign.payout_of(body)
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
            # written unless the one update landed, and the payout then shows it
            return 502, {"error": str(e)}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > consign.BODY_MAX:
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
                if not 0 <= n <= consign.BODY_MAX:
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
    elif all(conf.get(k) for k in ("PP_BASE", "PP_KEY", "PP_SECRET", "PP_WORK_SECRET", "PP_PAY_SECRET")):
        svc = Service(conf, Tenant(conf["PP_BASE"], conf["PP_KEY"], conf["PP_SECRET"]))
    else:
        raise SystemExit("set PP_BASE, PP_KEY, PP_SECRET, PP_WORK_SECRET and PP_PAY_SECRET (one retailer), or "
                         "IVN_LIBRARY_APP with a store (many retailers): the app does not start without a way to check a press")
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or conf.get("PORT") or 8161)), make_handler(svc))
    print(f"s61 consignment payouts on :{srv.server_port} ({'many retailers, ' + svc.app if svc.app else 'one retailer'}, "
          f"prefix {consign.PREFIX}; test modes {'ON' if svc.test_modes else 'off'})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
