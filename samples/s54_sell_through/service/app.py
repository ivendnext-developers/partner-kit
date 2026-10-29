#!/usr/bin/env python3
"""S54 — *Sell-through by size and colour*: the service behind the retailer's Desk button (standard library only).

    POST /sst/work      the retailer's signed press of *Work out sell-through* (``desk_action/1``)
                        →  200 {"message": …, "refresh": true}
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On a press it reads, with the app's own integration user's key (that user's rights, never the pressing user's): the
pressed run; its size and colour attributes' own order of values; the group's items with their attributes; and, for
each store side by side, two of the retailer's own reports through ``run_report`` (the kit's ``recipes/shop_reports.md``):
*POS Sale Report* (the till's units sold per item, returns taken off, since the run's date) and *Stock Projected Quantity*
(the stock per item, less the till's sales whose stock has not left yet). It writes the rows and the summary on
the run in one save, before it answers. A press that runs out of time before its save writes nothing.

ONE RETAILER (env or an env file):
    IVN_SHOP_URL, IVN_SHOP_KEY ("<api key>:<api secret>" of the integration user), IVN_WORK_SECRET (handed back at
    install as pp_sst:sub:work), PORT (8080)
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_sst), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
SST_PREFIX (default PP SST; IVENDNEXT SST for the library's app)

    python3 service/app.py service/.env.local
On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below).

The door (``Tenant``) and the press's checks are S49's (``samples/s49_post_sale_feedback/service/app.py``, kit ``main``
``c9f8c50``), with a ``method`` call added for ``run_report``: a defect here is a defect there — report it on the
Partner Programme's board.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import http.client
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
import function  # noqa: E402
import shops  # noqa: E402
import sst  # noqa: E402

SUB = "work"                         # the manifest's extension_subscriptions[].key
BUDGET_S = 7.0                       # the whole press; the retailer waits 10 seconds at most, and a function's cold start
                                     # (about 2.5 s, APPF run 9) comes first
READ_S = 5.0                         # one read, within the budget
SAVE_S = 4.0                         # the one save of the rows
SAVE_FROM = 1.0                      # seconds the save needs left: less, and nothing is written
READERS = 8                          # reads at once
RUN_REPORT = "ivendnext_mpos.api.v1.run_report"
ITEM_FIELDS = ["name", "variant_of", "attributes.attribute", "attributes.attribute_value"]
NOT_SET_UP = ("Sell-through is not set up yet: no key from this site has reached it. Ask your manager to check that the "
              "app's user has its key and, if the site could not reach the app, or a key was lost or changed, to press "
              "Connect again on the app.")
REFUSED = ("Sell-through may not read the run, the items or the two reports, or write the rows. Ask your manager to "
           "check the app's user, its role and the setup's report rights.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way
LATE = ("Your reports took the press's time, so nothing was written. Name fewer stores and press again.")
REPORT_REFUSED = ("Sell-through could not run {0}: check that the app's role is on it (Role Permission for Page and "
                  "Report), that the role has every right the setup names, that the report is switched on, and that each store still exists.")


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code = code            # the retailer's HTTP status, when it answered one
        self.kind = kind            # the retailer's error type (exc_type), never its message


class ReportRefused(TenantError):
    """A report refused the app's user: the framework says so with 417 (a right missing on a filter's record type, the
    report's record type, or the report switched off) or 403 (the role not on the report)."""

    def __init__(self, report: str, code: int | None):
        super().__init__(f"POST {report} -> HTTP {code}", code, "")
        self.report = report


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _kind(e: urllib.error.HTTPError) -> str:
    try:
        kind = json.loads(e.read(64 * 1024) or b"{}").get("exc_type")
    except (OSError, ValueError, http.client.HTTPException, AttributeError):
        return ""
    return kind if isinstance(kind, str) and kind.isidentifier() else ""


class Tenant:
    """The service's only door into iVendNext: the record API and ``run_report``, as the integration user."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = 3):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _open(self, method: str, url: str, what: str, body: bytes | None, ctype: str, timeout: float | None) -> dict:
        req = urllib.request.Request(url, data=body, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": ctype})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=timeout or self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind = _kind(e)
            e.close()
            raise TenantError(f"{method} {what} -> HTTP {e.code}", e.code, kind) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {what} -> {type(e).__name__}") from None   # the outcome is unknown

    def _call(self, method: str, path: str, body: dict | None = None, query: dict | None = None,
              timeout: float | None = None) -> dict:
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        return self._open(method, url, path.split("/")[0], json.dumps(body).encode() if body is not None else None,
                          "application/json", timeout)

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

    def rows(self, doctype: str, fields: list, filters: list, timeout: float | None = None, limit: int = 0) -> list:
        return self._data("GET", doctype, query={"fields": fields, "filters": filters, "limit_page_length": limit},
                          kind=list, timeout=timeout)

    def update(self, doctype: str, name: str, body: dict, timeout: float | None = None) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body, timeout=timeout)

    def report(self, name: str, filters: dict, timeout: float | None = None) -> dict:
        """``run_report``: the report's columns and rows, as the integration user reads them."""
        body = urllib.parse.urlencode({"report_name": name, "filters": json.dumps(filters)}).encode()
        try:
            return self._open("POST", f"{self.base}/api/method/{RUN_REPORT}", name, body,
                              "application/x-www-form-urlencoded", timeout)
        except TenantError as e:
            if e.code in (403, 417):
                raise ReportRefused(name, e.code) from None
            raise


def tenant_of(url: str, key: str) -> Tenant:
    """A retailer's door from the key the retailer's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).netloc or "").lower()


def today_utc(now: float | None = None) -> datetime.date:
    return datetime.datetime.fromtimestamp(now if now is not None else time.time(), datetime.timezone.utc).date()


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=None, clock=time.monotonic):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("SST_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but SST_PREFIX is not (IVENDNEXT SST for the App library's app)")
        sst.use_prefix(prefix or "PP SST")
        self.tenants, self.now, self.clock = tenants, now, clock
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            self.site = _host(conf["IVN_SHOP_URL"])
            self.secret = conf["IVN_WORK_SECRET"]
            self.tenant = tenant or tenant_of(conf["IVN_SHOP_URL"], conf["IVN_SHOP_KEY"])
        self._lock = threading.Lock()    # one retailer: one press at a time

    def retailer(self, site) -> tuple[str, list[bytes], object | None]:
        """(the retailer's site, the secrets its press may be signed with, newest first, its door: None until it handed
        over a user's key). A site the service does not know has no secrets."""
        if not self.app:
            return (self.site, [self.secret.encode()], self.tenant) if site == self.site else ("", [], None)
        site = shops.site_of(site)
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, f"{self.app}:sub:{SUB}")
        users = sorted(k for k in (record or {}).get("secrets") or {}
                       if k.startswith("user:") and k != "user:Administrator")    # the site never sends it; nor do we use it
        door = self.tenants(record["url"], record["secrets"][users[0]]) if record and users else None
        return site or "", secrets, door

    def left(self, t0: float, most: float = READ_S) -> float:
        rest = BUDGET_S - (self.clock() - t0)
        if rest <= 0:
            raise TenantError("the press ran out of time")
        return min(most, rest)

    def together(self, calls: list) -> list:
        """Each call's answer, in order, the calls made side by side; the first failure is raised."""
        if not calls:
            return []
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(READERS, len(calls))) as pool:
            return list(pool.map(lambda f: f(), calls))

    # ---- the press -------------------------------------------------------------------------------------------------

    def run(self, door, name: str) -> dict:
        t0 = self.clock()
        today = today_utc(self.now)
        run = sst.run_of(door.doc(sst.RUN, name, timeout=self.left(t0)), today)
        if isinstance(run, str):
            return sst.message(run, "warning")
        item_filters = [["item_group", "=", run.item_group], ["variant_of", "is", "set"], ["disabled", "=", 0]]
        if run.style:
            item_filters.append(["variant_of", "=", run.style])
        pos = {"report_type": "Item", "pos": "", "item_group": "", "item_code": "", "customer": "", "customer_group": "",
               "from_date": run.since.isoformat(), "to_date": (today + datetime.timedelta(days=1)).isoformat()}
        # to UTC's tomorrow: a store east of UTC dates its sales up to a day ahead of UTC's date, and none is later
        attrs = [run.size_attribute] + ([run.colour_attribute] if run.colour_attribute else [])
        n = len(run.stores)
        # every read side by side: a far retailer pays one round of waits, not one per read
        got = self.together(
            [lambda: door.rows("Item", ITEM_FIELDS, item_filters, timeout=self.left(t0), limit=sst.ITEMS_MAX)]
            + [lambda a=a: door.doc("Item Attribute", a, timeout=self.left(t0)) for a in attrs]
            + [lambda s=s: door.report(sst.POS_SALE_REPORT, dict(pos, warehouse=s), timeout=self.left(t0))
               for s in run.stores]
            + [lambda s=s: door.report(sst.STOCK_REPORT, {"warehouse": s, "item_group": run.item_group},
                                       timeout=self.left(t0))   # no company: the store decides it, and a store of
                                                                # another company would read as no stock
               for s in run.stores])
        item_rows, orders = got[0], [sst.order_of(a) for a in got[1:1 + len(attrs)]]
        sold_answers, stock_answers = got[1 + len(attrs):1 + len(attrs) + n], got[1 + len(attrs) + n:]
        if len(item_rows) >= sst.ITEMS_MAX:
            return sst.message(f"{name}: the group has more items than one run reads. Name one style, then press again.",
                               "warning")
        items = sst.variants_of(item_rows, run)
        if not items:
            what = f"the style {run.style}" if run.style else f"the group {run.item_group}"
            return sst.message(f"{name}: {what} has no variants with a {run.size_attribute}. Check the group, the style "
                               "and the size attribute, then press again.", "warning")
        try:
            sold = {s: sst.sold_of(a, items) for s, a in zip(run.stores, sold_answers)}
            stock = {s: sst.stock_of(a, items, s) for s, a in zip(run.stores, stock_answers)}
        except ValueError as e:
            return sst.message(f"{name}: {e}. Nothing was written.", "warning")
        rows = sst.rows_of(items, sold, stock, run, orders[0], orders[1] if len(orders) > 1 else {})
        if len(rows) > sst.ROWS_MAX:
            return sst.message(f"{name}: {len(rows)} rows, more than the {sst.ROWS_MAX} one run holds. Name one style, "
                               "or fewer stores, and press again.", "warning")
        if BUDGET_S - (self.clock() - t0) < SAVE_FROM:
            return sst.message(LATE, "warning")
        summary = sst.summary_of(rows, run) if rows else (
            f"Nothing sold since {run.since.isoformat()} and nothing in stock in these stores.")
        door.update(sst.RUN, name, {"rows": rows, "summary": summary}, timeout=self.left(t0, SAVE_S))
        return sst.message(f"{len(rows)} row{'' if len(rows) == 1 else 's'} written. " + summary)

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.retailer(headers.get(shops.SITE_HEADER) if self.app else self.site)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(sst.verify(ts, sig, raw, s.decode()) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            name, _user = sst.run_of_press(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if door is None:
            return 200, sst.message(NOT_SET_UP, "warning")
        try:
            if not self.app:
                with self._lock:        # one retailer: one press at a time
                    return 200, self.run(door, name)
            return 200, self.run(door, name)
        except ReportRefused as e:      # before the 401/403 arm: a report names what to fix
            return 200, sst.message(REPORT_REFUSED.format(e.report), "warning")
        except TenantError as e:
            if e.code in (401, 403):    # the retailer refused the app's user: say so
                return 200, sst.message(REFUSED + (CONNECT_AGAIN if self.app else ""), "warning")
            if e.code == 404:
                return 200, sst.message(f"{name}, its size or colour attribute, or a report was not found.", "warning")
            if str(e).endswith("ran out of time"):
                return 200, sst.message(LATE, "warning")
            # the retailer tells the user "did not answer in time. Check the record before you try again"
            return 502, {"error": str(e)}

    # ---- every call ------------------------------------------------------------------------------------------------

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, bytes, dict]:
        """Every call: (status, body, headers). The web server and the function entry both use it."""
        path = path.split("?", 1)[0]
        if method == "GET":
            return _json(200, {"ok": 1}) if path == "/health" else _json(404, {"error": "not found"})
        if method != "POST":
            return _json(404, {"error": "not found"})
        if raw is None or len(raw) > sst.BODY_MAX:
            return _json(413, {"error": "too large"})
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return _json(*shops.handle(self.store, self.app, path, headers, raw))
        if path == "/sst/work":
            return _json(*self.press(headers, raw))
        return _json(404, {"error": "not found"})


def _json(code: int, body: dict) -> tuple[int, bytes, dict]:
    return code, json.dumps(body).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store",
                                             "X-Content-Type-Options": "nosniff"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
    """One call, and one log line (the route, the status and the time; never the body or a key)."""
    t0 = time.monotonic()
    code, body, hdrs = svc.handle(method, path, headers, raw)
    print(json.dumps({"request": (headers.get("X-iVendNext-Request-Id") or "-")[:40], "route": path.split("?", 1)[0][:20],
                      "status": code, "ms": int((time.monotonic() - t0) * 1000)}), flush=True)
    return code, body, hdrs


def make_server(svc: Service, port: int):
    class Handler(BaseHTTPRequestHandler):
        timeout = 10

        def _answer(self, method: str):
            raw = None
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n < 0 or n > sst.BODY_MAX:
                    return self._send(*_json(413, {"error": "too large"}))
                raw = self.rfile.read(n)
            self._send(*handle(svc, method, self.path, self.headers, raw))

        def _send(self, code: int, body: bytes, hdrs: dict):
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._answer("GET")

        def do_POST(self):
            self._answer("POST")

        def log_message(self, fmt, *args):     # the server's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


_KEPT: dict = {}   # the function's settings, opened on the first call of each copy and kept while it lives


def lambda_handler(event, context=None):
    """As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b)."""
    if "svc" not in _KEPT:
        _KEPT["svc"] = Service(dict(os.environ))
    method, path, headers, raw = function.request(event)
    code, body, hdrs = handle(_KEPT["svc"], method, path, headers, raw)
    return {"statusCode": code, "statusDescription": f"{code} {'OK' if code == 200 else 'Error'}",
            "isBase64Encoded": False, "headers": hdrs, "body": body.decode("utf-8")}


def env_file(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env_file(sys.argv[1]) if len(sys.argv) > 1 else {}))
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_WORK_SECRET"))):
        raise SystemExit("set IVN_SHOP_URL, IVN_SHOP_KEY and IVN_WORK_SECRET (one retailer), or IVN_LIBRARY_APP with a "
                         "store (many retailers): the app does not start without a way to check a press")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "prefix": sst.PREFIX}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
