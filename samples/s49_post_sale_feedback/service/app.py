#!/usr/bin/env python3
"""S49 — *Post-sale feedback*: the service behind the retailer's Desk button and the customer's answer page (standard
library only).

    POST /psf/send      the retailer's signed press of *Send feedback requests* (``desk_action/1``)
                        →  200 {"message": …, "refresh": true}
    GET  /              the customer's page (its address carries #s=<the retailer's site>&t=<the sale>.<signature>)
    GET  /page.js · /page.css
    POST /psf/open      {"s", "t"}                                  →  200 {"state", "name", "date", "question", "answers"}
    POST /psf/answer    {"s", "t", "answer": 0-2 or null, "comment", "stop"}  →  200 the same, after the write
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On a press it reads, with the app's own integration user's key (that user's rights, never the pressing user's): the
pressed rules, every POS Profile's walk-in customer and store, each rule's submitted till sales of its last days
received since its last press (oldest first), the requests already made for those days, the customers who asked to
stop, and the mobile number and e-mail of the customers whose sale carries neither. It writes one request per sale to
ask, each holding the customer's signed link, several at once, until ``WRITE_UNTIL`` seconds into the press; then it
moves each rule's *asked up to* so the next press starts where this one stopped. The retailer's own Notification on
the request sends the message. A press that runs out of time before its writes writes nothing.

The page holds no secret. Its calls carry the link's ``s`` and ``t``; the service checks ``t``'s signature with the
retailer's press secret before it reads anything, so a guessed link never reaches the retailer's iVendNext. Then it
reads that one request and its rule, and writes the answer once (with the request's ``modified`` as read).

ONE RETAILER (env or an env file):
    IVN_SHOP_URL, IVN_SHOP_KEY ("<api key>:<api secret>" of the integration user), IVN_SEND_SECRET (handed back at
    install as pp_psf:sub:send), PSF_PAGE_URL (where this service's page is reached), PORT (8080)
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_psf), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
PSF_PREFIX (default PP PSF; IVENDNEXT PSF for the library's app)

    python3 service/app.py service/.env.local
On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below).
"""

from __future__ import annotations

import concurrent.futures
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
import feedback as fb  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

SUB = "send"                         # the manifest's extension_subscriptions[].key
STALE, DUPLICATE = "TimestampMismatchError", "DuplicateEntryError"   # the retailer's error types the service branches on
REFUSED_ONE = {"InvalidPhoneNumberError", "InvalidEmailAddressError", "LinkValidationError"}   # this one request's values:
                                     # any other refusal (a Notification's condition that fails, a rule of the retailer's
                                     # own on the request) refuses every request, and the next press tries them again
BUDGET_S = 7.0                       # the whole press; the retailer waits 10 seconds at most, and a function's cold start
                                     # (about 2.5 s, APPF run 9) comes first
READ_S = 4.0                         # one read, within the budget
WRITE_UNTIL = 4.5                    # no new request is started after this many seconds into the press
WRITE_S = 2.0                        # one request's save (the retailer's Notification sends inside it)
WRITERS = 8                          # requests saved at once
SALES_MAX = 500                      # sales read for one rule in one press; more wait for the next press
SALE_FIELDS = ["name", "customer", "customer_name", "contact_mobile", "contact_email", "pos_profile", "posting_date",
               "docstatus", "is_return", "creation"]
RULE_FIELDS = ["name", "enabled", "shown_name", "question", "answer_good", "answer_ok", "answer_bad", "look_back_days",
               "open_days", "asked_up_to", "profiles.pos_profile"]
CUSTOMER_FIELDS = ["name", "mobile_no", "email_id", "custom_phone_no", "custom_email"]
STATIC = {"/": ("page.html", "text/html; charset=utf-8"), "/page.js": ("page.js", "text/javascript; charset=utf-8"),
          "/page.css": ("page.css", "text/css; charset=utf-8")}
NOT_SET_UP = ("Post-sale feedback is not set up yet. Ask your manager to choose its user on the app's feed and press "
              "Connect again.")
REFUSED = ("Post-sale feedback may not read the sales or write the requests. Ask your manager to check the app's user, "
           "its role and its API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code = code            # the retailer's HTTP status, when it answered one
        self.kind = kind            # the retailer's error type (exc_type), never its message


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
    """The service's only door into iVendNext: the record API, as the integration user (S44's door, with an insert)."""

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

    def rows(self, doctype: str, fields: list, filters: list, timeout: float | None = None, order_by: str = "",
             limit: int = 0) -> list:
        q = {"fields": fields, "filters": filters, "limit_page_length": limit}
        if order_by:
            q["order_by"] = order_by
        return self._data("GET", doctype, query=q, kind=list, timeout=timeout)

    def insert(self, doctype: str, body: dict, timeout: float | None = None) -> dict:
        return self._data("POST", doctype, body, timeout=timeout)

    def update(self, doctype: str, name: str, body: dict, timeout: float | None = None) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body, timeout=timeout)


def tenant_of(url: str, key: str) -> Tenant:
    """A retailer's door from the key it handed over on Connect again ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).netloc or "").lower()


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=None, clock=time.monotonic):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("PSF_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but PSF_PREFIX is not (IVENDNEXT PSF for the App library's app)")
        fb.use_prefix(prefix or "PP PSF")
        self.page = (conf.get("PSF_PAGE_URL") or "").strip()
        if not self.page.startswith(("https://", "http://")):
            raise SystemExit("set PSF_PAGE_URL, where customers reach this service's page (its links point there)")
        self.tenants, self.now, self.clock = tenants, now, clock
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            self.site = _host(conf["IVN_SHOP_URL"])
            self.secret = conf["IVN_SEND_SECRET"]
            self.tenant = tenant or tenant_of(conf["IVN_SHOP_URL"], conf["IVN_SHOP_KEY"])
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []
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
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(WRITERS, len(calls))) as pool:
            return list(pool.map(lambda f: f(), calls))

    # ---- the press -------------------------------------------------------------------------------------------------

    def run(self, door, names: list[str], site: str, secret: bytes) -> dict:
        t0 = self.clock()
        today = fb.today_utc(self.now)
        found = fb.rules_from_rows(door.rows(fb.RULE, RULE_FIELDS, [["name", "in", names]], timeout=self.left(t0)))
        rules, problems = [], [f"{n} was not found." for n in names if n not in found]
        for n in names:
            if n in found:
                r = fb.rule_of(found[n])
                (problems if isinstance(r, str) else rules).append(r)
        if not rules:
            return fb.message(" ".join(problems), "warning")
        first = min(fb.since(r, today) for r in rules)

        def sales(r):
            f = [["docstatus", "=", 1], ["is_return", "=", 0], ["posting_date", ">=", fb.since(r, today).isoformat()]]
            if r.profiles:
                f.append(["pos_profile", "in", r.profiles])
            if r.asked_up_to:
                f.append(["creation", ">=", r.asked_up_to])
            return door.rows("POS Invoice", SALE_FIELDS, f, timeout=self.left(t0), order_by="creation asc", limit=SALES_MAX)

        # the reads that need only the rules, side by side: a far retailer pays one round of waits, not seven
        got = self.together(
            [lambda: door.rows("POS Profile", ["name", "customer", "warehouse"], [], timeout=self.left(t0)),
             lambda: door.rows(fb.REQUEST, ["name", "customer"], [["sale_date", ">=", first.isoformat()]], timeout=self.left(t0)),
             lambda: door.rows(fb.REQUEST, ["customer"], [["asked_to_stop", "=", 1]], timeout=self.left(t0))]
            + [lambda r=r: sales(r) for r in rules])
        tills, done, stops, sales_of = got[0], got[1], got[2], {r.name: s for r, s in zip(rules, got[3:])}
        walk_ins = {t.get("customer") for t in tills if isinstance(t, dict) and t.get("customer")}
        store = {t.get("name"): t.get("warehouse") or "" for t in tills if isinstance(t, dict)}
        asked = set()                                   # the sales, and the customers, already asked in these days
        for q in done:
            asked.update(v for v in (q.get("name"), q.get("customer")) if v)
        stopped = {q.get("customer") for q in stops}
        bare = sorted({s.get("customer") for ss in sales_of.values() for s in ss if isinstance(s, dict) and s.get("customer")
                       and not (fb.phone_of(s.get("contact_mobile")) or fb.email_of(s.get("contact_email")))})
        customers = {}
        for rows in self.together([lambda c=bare[i:i + 50]: door.rows("Customer", CUSTOMER_FIELDS, [["name", "in", c]],
                                                                        timeout=self.left(t0))
                                   for i in range(0, len(bare), 50)]):      # 50 names a read keeps the address short
            customers.update(fb.contacts_of(rows))
        self.left(t0)                                    # out of time after the reads: nothing is written
        taken, counts, plan = set(), {"asked": 0, "stopped": 0, "no_contact": 0}, []
        for r in rules:
            chosen, c = fb.choose(sales_of[r.name], r, walk_ins, asked, stopped, customers, taken, today)
            for k in counts:
                counts[k] += c[k]
            plan += [(r, s, m, e) for s, m, e in chosen]
        made, failed, unmade = self.write(door, plan, site, secret, store, t0)
        for r in rules:
            mark = fb.mark_after(r, sales_of[r.name], unmade.get(r.name, []))
            if mark != r.asked_up_to:
                try:
                    door.update(fb.RULE, r.name, {"asked_up_to": mark}, timeout=self.left(t0, WRITE_S))
                except TenantError:
                    problems.append(f"{r.name}: where the next press starts could not be saved; it reads these days again.")
        left = any(unmade.values()) or any(len(sales_of[r.name]) >= SALES_MAX for r in rules)
        if plan and not made and not failed:
            problems.append("Reading your sales took the press's time, so none was made yet.")
        return fb.press_answer(made, counts, failed, left, problems)

    def write(self, door, plan: list, site: str, secret: bytes, store: dict, t0: float) -> tuple[int, int, dict]:
        """Save the requests several at once until WRITE_UNTIL: (made, refused or unknown, the sales not made by rule)."""
        made, failed, unmade = 0, 0, {}

        def save(item):
            r, s, mobile, email = item
            if self.clock() - t0 >= WRITE_UNTIL:
                return item, "late"
            body = fb.request_of(s, r, mobile, email, store.get(s.get("pos_profile"), ""),
                                 fb.link_of(self.page, site, s["name"], secret))
            try:
                door.insert(fb.REQUEST, body, timeout=WRITE_S)
                return item, "made"
            except TenantError as e:
                if e.kind == DUPLICATE:          # made before (another press at the same moment): asked
                    return item, "made"
                if e.kind in REFUSED_ONE:        # the retailer refused this one request (a number its Phone field
                    return item, "refused"       # refuses): never tried again, or it would hold the rule's place
                return item, "failed"            # no answer, or a fault: the next press tries it again

        with concurrent.futures.ThreadPoolExecutor(max_workers=WRITERS) as pool:
            for item, how in pool.map(save, plan):
                if how == "made":
                    made += 1
                    continue
                failed += how != "late"
                if how != "refused":
                    unmade.setdefault(item[0].name, []).append(item[1])
        return made, failed, unmade

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.retailer(headers.get(shops.SITE_HEADER) if self.app else self.site)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(fb.verify(ts, sig, raw, s.decode()) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            names, _user = fb.rules_of_press(body)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, fb.message(NOT_SET_UP, "warning")
        try:
            if not self.app:
                with self._lock:        # one retailer: one press at a time
                    return 200, self.run(door, names, site, secrets[0])
            return 200, self.run(door, names, site, secrets[0])
        except TenantError as e:
            if e.code in (401, 403):    # the retailer refused the app's user: say so
                return 200, fb.message(REFUSED + (CONNECT_AGAIN if self.app else ""), "warning")
            # the retailer tells the user "did not answer in time. Check the record before you try again"; requests
            # already saved are found asked by the next press
            return 502, {"error": str(e)}

    # ---- the customer's page ---------------------------------------------------------------------------------------

    def page_call(self, path: str, raw: bytes) -> tuple[int, dict]:
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("s"), str):
            return 400, {"state": "unknown"}
        try:
            site, secrets, door = self.retailer(body["s"])
        except Exception:               # noqa: BLE001 — the shops store did not answer
            return 503, {"state": "unavailable"}
        sale = fb.sale_of_token(site, body.get("t"), secrets) if site else None
        if not sale:                    # the same answer for a retailer the app does not know and a bad signature
            return 404, {"state": "unknown"}
        if door is None:
            return 503, {"state": "unavailable"}
        try:
            if path == "/psf/open":
                return 200, self.view(door, sale)[0]
            return self.answer(door, sale, body)
        except TenantError as e:
            return (404, {"state": "unknown"}) if e.code == 404 else (503, {"state": "unavailable"})

    def view(self, door, sale: str) -> tuple[dict, dict]:
        req = door.doc(fb.REQUEST, sale, timeout=READ_S)
        try:
            rule = door.doc(fb.RULE, req.get("rule") or "", timeout=READ_S) if req.get("rule") else {}
        except TenantError as e:
            if e.code != 404:
                raise
            rule = {}                   # a rule deleted since: the app's own words
        return fb.page_of(req, rule, fb.today_utc(self.now)), req

    def answer(self, door, sale: str, body: dict) -> tuple[int, dict]:
        try:
            a, comment, stop = fb.answer_of(body)
        except ValueError:
            return 400, {"state": "unknown"}
        page, req = self.view(door, sale)
        write = {"modified": req.get("modified")}
        if stop:
            write["asked_to_stop"] = 1
        if a is not None and page["state"] == "open":
            write.update(answer=fb.ANSWERS[a], comment=comment, status="Answered",
                         answered_at=fb.now_text(self.now if self.now is not None else time.time()))
        if len(write) == 1:             # nothing to write: an answer to a link already answered or past its last day
            return 200, page
        try:
            door.update(fb.REQUEST, sale, write, timeout=READ_S)
        except TenantError as e:
            if e.kind != STALE:         # another tap saved first: show what it saved
                raise
        return 200, self.view(door, sale)[0]

    # ---- every call ------------------------------------------------------------------------------------------------

    def csp(self) -> str:
        return ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; "
                "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, bytes, dict]:
        """Every call: (status, body, headers). The web server and the function entry both use it."""
        path = path.split("?", 1)[0]
        if method == "GET":
            if path == "/health":
                return _json(200, {"ok": 1})
            if path in STATIC:
                fname, ctype = STATIC[path]
                with open(os.path.join(HERE, fname), "rb") as f:
                    data = f.read()
                return 200, data, {"Content-Type": ctype, "Content-Security-Policy": self.csp(),
                                   "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
                                   "Cache-Control": "no-cache"}
            return _json(404, {"error": "not found"})
        if method != "POST":
            return _json(404, {"error": "not found"})
        if raw is None or len(raw) > fb.BODY_MAX:
            return _json(413, {"error": "too large"})
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return _json(*shops.handle(self.store, self.app, path, headers, raw))
        if path == "/psf/send":
            return _json(*self.press(headers, raw))
        if path in ("/psf/open", "/psf/answer"):
            if len(raw) > fb.PAGE_BODY_MAX:
                return _json(413, {"state": "unknown"})
            return _json(*self.page_call(path, raw))
        return _json(404, {"error": "not found"})


def _json(code: int, body: dict) -> tuple[int, bytes, dict]:
    return code, json.dumps(body).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store",
                                             "X-Content-Type-Options": "nosniff"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
    """One call, and one log line (the route, the status and the time; never the body, a link, a number or a key)."""
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
                if n < 0 or n > fb.BODY_MAX:
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
            if self.path == "/test/received" and svc.test_modes and self.headers.get("X-PP-Admin") == svc.admin:
                return self._send(*_json(200, {"received": svc.received}))
            self._answer("GET")

        def do_POST(self):
            self._answer("POST")

        def log_message(self, fmt, *args):     # the server's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


_KEPT: dict = {}   # the function's settings, opened on the first call of each copy and kept while it lives


def lambda_handler(event, context=None):
    """As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b). The template's ``function``
    reads the load balancer's call; the answer carries its own content type, because this app also serves a page."""
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
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_SEND_SECRET"))):
        raise SystemExit("set IVN_SHOP_URL, IVN_SHOP_KEY and IVN_SEND_SECRET (one retailer), or IVN_LIBRARY_APP with a "
                         "store (many retailers): the app does not start without a way to check a press")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "prefix": fb.PREFIX,
                      "test_modes": "on" if svc.test_modes else "off"}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
