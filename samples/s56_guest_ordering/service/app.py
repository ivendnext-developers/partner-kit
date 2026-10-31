#!/usr/bin/env python3
"""S56 — *Guest ordering*: the service behind the retailer's *Make code* button and the guest's ordering page (standard
library only).

    POST /gor/code      the retailer's signed press of *Make code* (``desk_action/1``): each ticked code record gets a
                        new number, its signed link and its QR picture        →  200 {"message": …, "refresh": true}
    GET  /              the guest's page (its address carries #s=<the retailer's site>&t=<code>.<number>.<signature>)
    GET  /page.js · /page.css
    POST /gor/menu      {"s", "t"}                                  →  200 {"state": "open", "where", "menu", …}
    POST /gor/order     {"s", "t", "key", "lines"}                  →  200 {"state": "sent" | "refused" | "wait", …}
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below).

**The guest is never trusted with a choice the shop makes.** The page holds no secret. Each call carries the link's
``s`` and ``t``; the service checks ``t``'s signature with the retailer's *Make code* secret before it reads anything,
then reads the code record (as the app's own user) and refuses a code whose number moved on (a code that leaked and was
made again). The store, the table and the register come from the record and the store's row, never from the page.

**An order** is one press of *Send order* with a fresh random key the page made. Under a claim on the code in the
service's own table (one order per code every ``SPACING_S`` seconds, every copy of the function sees it), the service
reads the store's floor: no check at the table → it opens one; one → it adds to it; more → it refuses. The door's two
keys are made from the page's key, so a retry opens nothing twice and adds nothing twice. A kiosk's order opens a tab
named by a code made from the same key. Nothing is priced, sent to the kitchen or paid here.

ONE RETAILER (env or an env file):
    IVN_SHOP_URL, IVN_SHOP_KEY ("<api key>:<api secret>" of the app's user), IVN_CODE_SECRET (handed back at install as
    pp_gor:sub:code), GOR_PAGE_URL (where this service's page is reached), PORT (8080)
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_gor), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
GOR_PREFIX (default PP GOR; IVENDNEXT GOR for the library's app)

    python3 service/app.py service/.env.local
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
import function  # noqa: E402
import gor  # noqa: E402
import qr  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

SUB = "code"                         # the manifest's extension_subscriptions[].key
DOOR = "/api/method/ivendnext_mpos.api.v1."     # the till's partner API (its open-check door and its line pricer)
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
BUDGET_S = 7.0                       # a press, or a guest's call: the shop waits 10 seconds for a press
READ_S = 4.0                         # one read, within the budget
PRICERS = 8                          # prices asked at once
MENU_KEEP_S = 120                    # a store's menu is read again after this
MENU_CACHE_MAX = 200                 # stores whose menu one copy keeps
MENU_SHORT_S = 10                    # a menu some of whose prices the pricer did not give in time is kept only this long
LATE = object()                      # a price the time budget skipped: asked again at the next read, alone
CODE_KEEP_S = 15                     # a verified code and its store's row, kept so a flood of calls on one code reads
                                     # the retailer once per copy this often (a code made again stops within this time)
STATIC = {"/": ("page.html", "text/html; charset=utf-8"), "/page.js": ("page.js", "text/javascript; charset=utf-8"),
          "/page.css": ("page.css", "text/css; charset=utf-8")}
CODE_FIELDS = ["name", "kind", "store", "place", "kiosk_name", "number", "modified"]
ROW_FIELDS = ["parent", "store", "register", "tables_on", "kiosk_on", "course", "most_lines", "most_qty"]
UNASSIGNED = ("ProfileNotAssignedError", "AssignedProfileDisabledError", "DuplicateStoreAssignmentError",
              "StoreAssignmentIncompleteError")
SET_UP = ("TableServiceOffError", "PermissionError", "DeviceRequiredError") + UNASSIGNED
NOT_SET_UP = ("Guest ordering is not set up yet: no key from this site has reached it. Ask your manager to check that "
              "the app's user has its key and, if the site could not reach the app, or a key was lost or changed, to "
              "press Connect again on the app.")
REFUSED = ("Guest ordering may not read or write what it needs. Ask your manager to check the app's user, its role and "
           "its API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way
# the guest's words (the page shows them; the page's own words are translated there)
ASK_STAFF = "This table cannot take orders from your phone right now. Please ask a member of staff."
ASK_STAFF_KIOSK = "This kiosk cannot take orders right now. Please order at the counter."
MANY_BILLS = "This table has more than one bill open. Please ask your server to take your order."
SENT_TWICE = "This order was already sent once. Please ask a member of staff to check the bill."
WAIT = "An order was sent from here a moment ago. Please send yours again in a few seconds."
ITEM_REFUSED = "Something in your order cannot be ordered now. Please ask a member of staff."
CHANGED = "The bill changed a moment ago. Please send your order again."
PAYING = "This table's bill is being paid. Please ask your server."
SENT_TABLE = "Your order is on your table's bill. Your server will confirm it with you."
SENT_KIOSK = "Your order is {code}. Please pay at the counter and keep your receipt."


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code = code            # the retailer's HTTP status, when it answered one
        self.kind = kind            # the retailer's error type (exc_type), never its message

    @property
    def refused(self) -> bool:
        """The retailer answered and refused: nothing was written (never a lost answer or a fault of the shop's)."""
        return self.code is not None and 400 <= self.code < 500


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
    """The service's only door into iVendNext, as the app's own user (token key:secret): the record API for its own
    records and the menu's reads, and the till's partner API for the open-check door and the line pricer."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = READ_S):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _open(self, method: str, url: str, body: dict | None, what: str):
        req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None, method=method,
                                     headers={"Authorization": self._auth, "Accept": "application/json",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=self.timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            kind = _kind(e)
            e.close()
            raise TenantError(f"{method} {what} -> HTTP {e.code}", e.code, kind) from None
        except (OSError, ValueError, http.client.HTTPException) as e:     # OSError holds URLError, timeouts, TLS
            raise TenantError(f"{method} {what} -> {type(e).__name__}") from None   # the outcome is unknown

    def _data(self, method: str, path: str, body: dict | None = None, query: dict | None = None, kind=dict):
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        what = path.split("/")[0]
        try:
            data = self._open(method, url, body, what)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {what} -> an answer with no data") from None
        if not isinstance(data, kind):
            raise TenantError(f"{method} {what} -> an answer with no data")
        return data

    def doc(self, doctype: str, name: str) -> dict:
        return self._data("GET", f"{doctype}/{name}")

    def rows(self, doctype: str, fields: list, filters: list, parent: str | None = None, limit: int = 500,
             order_by: str = "") -> list:
        q = {"fields": fields, "filters": filters, "limit_page_length": limit}
        if order_by:
            q["order_by"] = order_by
        if parent:
            q["parent"] = parent
        return [r for r in self._data("GET", doctype, query=q, kind=list) if isinstance(r, dict)]

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)

    def call(self, verb: str, body: dict | None = None, query: dict | None = None):
        """One of the till's partner calls; its answer (``message``)."""
        url = self.base + DOOR + verb + ("?" + urllib.parse.urlencode(query) if query else "")
        out = self._open("POST" if body is not None else "GET", url, body, verb)
        return out.get("message") if isinstance(out, dict) else None


def tenant_of(url: str, key: str) -> Tenant:
    """A retailer's door from the key the retailer's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).netloc or "").lower()


class Busy(Exception):
    """Another order for this code is being sent, or was sent a moment ago."""


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=time.time, clock=time.monotonic):
        self.app = oneshop.value(conf, oneshop.MANY)
        prefix = (conf.get("GOR_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but GOR_PREFIX is not (IVENDNEXT GOR for the App library's app)")
        gor.use_prefix(prefix or "PP GOR")
        self.page = (conf.get("GOR_PAGE_URL") or "").strip()
        if not self.page.startswith(("https://", "http://")):
            raise SystemExit("set GOR_PAGE_URL, where guests reach this service's page (each code's link points there)")
        self.tenants, self.now, self.clock = tenants, now, clock
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            one = oneshop.settings(conf, ["IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_CODE_SECRET"])
            self.site = _host(one["IVN_SHOP_URL"])
            self.secret = one["IVN_CODE_SECRET"]
            self.tenant = tenant or tenant_of(one["IVN_SHOP_URL"], one["IVN_SHOP_KEY"])
            self._spaced: dict[str, float] = {}
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []
        self._menus: dict[tuple, tuple] = {}
        self._codes: dict[tuple, tuple] = {}
        self._lock = threading.Lock()

    def retailer(self, site) -> tuple[str, list[bytes], object | None]:
        """(the retailer's site, the secrets its press and its codes may be signed with, newest first, its door: None
        until it handed over a user's key). A site the service does not know has no secrets."""
        if not self.app:
            return (self.site, [self.secret.encode()], self.tenant) if site == self.site else ("", [], None)
        site = shops.site_of(site)
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, f"{self.app}:sub:{SUB}")
        users = sorted(k for k in (record or {}).get("secrets") or {}
                       if k.startswith("user:") and k != "user:Administrator")    # the site never sends it; nor do we use it
        door = self.tenants(record["url"], record["secrets"][users[0]]) if record and users else None
        return site or "", secrets, door

    def space(self, site: str, c: dict):
        """One order per table (or kiosk) every ``SPACING_S`` seconds: a claim every copy of the function sees (the shops
        table's conditional write), or this process's own clock for one retailer. ``Busy`` when it is taken. A table's
        claim names its store and place, so two code records for one table share it."""
        where = f"{c.get('store')}|{c.get('place')}" if c.get("kind") == gor.KIND_TABLE else c.get("name")
        name = f"gor|{site}|{where}"
        now = self.now()
        if self.app:
            if not self.store.claim(name, now, gor.SPACING_S):
                raise Busy()
            return
        with self._lock:
            if self._spaced.get(name, 0) > now - gor.SPACING_S:
                raise Busy()
            self._spaced[name] = now

    # ── the store's row and its register ──
    def row(self, door, store: str) -> dict | None:
        rows = door.rows(gor.dt("Store"), ROW_FIELDS, [["store", "=", store]], parent=gor.dt("Settings"))
        return rows[0] if rows else None

    def code(self, door, record: str, number: int | None = None) -> dict | None:
        """The code record, or None when it is gone or (``number`` given) its number moved on."""
        try:
            c = door.doc(gor.dt("Code"), record)
        except TenantError as e:
            if e.code == 404:
                return None
            raise
        if number is not None and (gor.num(c.get("number")) != number or c.get("made_for") != gor.made_for(c)):
            return None                 # made again since, or its kind, store, table or kiosk changed since it was made
        return c

    def menu(self, door, site: str, store: str, register: str) -> tuple[list[dict], str]:
        """The register's menu and its currency, kept ``MENU_KEEP_S`` seconds per store."""
        key = (site, store, register)
        kept = self._menus.get(key)
        if kept and self.clock() - kept[0] < MENU_KEEP_S:
            return kept[1], kept[2]
        known = {c: p for c, p in (kept[3] if kept else {}).items() if p is not LATE}   # a late menu prices what it missed
        t0 = self.clock()
        reg = door.doc("POS Profile", register)
        groups = [g.get("item_group") for g in reg.get("item_groups") or [] if isinstance(g, dict) and g.get("item_group")]
        if not groups:
            raise gor.Refused("")                         # no menu groups on the register: the guest asks staff
        items = door.rows("Item", ["name", "item_name", "item_group"],
                          [["item_group", "in", groups], ["is_sales_item", "=", 1], ["disabled", "=", 0],
                           ["has_variants", "=", 0], ["custom_is_gift_card", "=", 0], ["custom_mpos_option_only", "=", 0]],
                          limit=gor.MENU_MAX, order_by="item_name asc")
        dishes = [i["name"] for i in items if isinstance(i.get("name"), str)]
        rows = door.rows("Cross Selling Product Detail",
                         ["parent", "idx", "item_code", "item_name", "price_type", "price", "discount_type", "discount",
                          "custom_mpos_option_group"],
                         [["parent", "in", dishes], ["custom_mpos_option_group", "is", "set"]], parent="Item",
                         limit=2000) if dishes else []
        names = sorted({r.get("custom_mpos_option_group") for r in rows if r.get("custom_mpos_option_group")})
        meta = {g["name"]: g for g in door.rows("Retail Option Group",
                                                ["name", "display_name", "min_picks", "max_picks", "enabled"],
                                                [["name", "in", names]])} if names else {}
        need = dishes + sorted({r["item_code"] for r in rows if r.get("item_code") and r.get("price_type") != "Amount"})
        need = list(dict.fromkeys(need))
        if not (kept and any(p is LATE for p in kept[3].values())):
            known = {}                                    # a full read prices every item again
        prices = {**{c: known[c] for c in need if c in known},
                  **self.prices(door, reg, [c for c in need if c not in known], t0)}
        late = any(v is LATE for v in prices.values())    # kept briefly: what the budget skipped is priced next read
        menu = gor.menu_of(items, rows, meta, {c: (None if p is LATE else p) for c, p in prices.items()}, groups)
        with self._lock:
            if len(self._menus) >= MENU_CACHE_MAX:
                self._menus.pop(next(iter(self._menus)))
            kept_at = self.clock() - (MENU_KEEP_S - MENU_SHORT_S if late else 0)
            self._menus[key] = (kept_at, menu, reg.get("currency") or "", prices)
        return menu, reg.get("currency") or ""

    def prices(self, door, reg: dict, codes: list[str], t0: float) -> dict:
        """One unit's list price of each item at the register (its price list, company, currency and walk-in customer,
        no price rule), side by side. A price the pricer refuses stays blank on the menu; one the time budget skipped is
        ``LATE``.
        ⛔ Never a ``rate``: given one, the shop's pricer may write a price row."""
        def one(code):
            if self.clock() - t0 > BUDGET_S - 2:
                return code, LATE
            args = {"item_code": code, "qty": 1, "doctype": "Sales Invoice", "company": reg.get("company"),
                    "selling_price_list": reg.get("selling_price_list"), "currency": reg.get("currency"),
                    "conversion_rate": 1, "plc_conversion_rate": 1, "ignore_pricing_rule": 1,
                    "customer": reg.get("customer"), "warehouse": reg.get("warehouse")}
            try:
                got = door.call("get_item_details", {"args": {k: v for k, v in args.items() if v not in (None, "")}})
            except TenantError:
                return code, None
            return code, (got or {}).get("price_list_rate") if isinstance(got, dict) else None
        if not codes:
            return {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(PRICERS, len(codes))) as pool:
            return dict(pool.map(one, codes))

    # ── the press: Make code ──
    def make_codes(self, door, names: list[str], site: str, secret: bytes) -> dict:
        t0, done, problems = self.clock(), [], []
        floors: dict[str, dict] = {}
        for name in names:
            if self.clock() - t0 > BUDGET_S - 2:
                problems.append(f"{len(names) - len(done) - len(problems)} more were not made: press again for them.")
                break
            c = self.code(door, name)
            if c is None:
                problems.append(f"{name} was not found.")
                continue
            if c.get("kind") not in (gor.KIND_TABLE, gor.KIND_KIOSK) or not c.get("store"):
                problems.append(f"{name}: choose its kind and its store, save, then press Make code.")
                continue
            if c["kind"] == gor.KIND_TABLE:
                if not c.get("place"):
                    problems.append(f"{name}: choose its table, save, then press Make code.")
                    continue
                if c["store"] not in floors:
                    floors[c["store"]] = door.call("floor_status", query={"store": c["store"]}) or {}
                if gor.place_of(floors[c["store"]], c["place"]) is None:
                    problems.append(f"{name}: {c['place']} is not an active table of {c['store']}'s floor.")
                    continue
            elif not (c.get("kiosk_name") or "").strip():
                problems.append(f"{name}: name the kiosk, save, then press Make code.")
                continue
            number = gor.num(c.get("number")) + 1
            link = gor.link_of(self.page, site, name, number, secret)
            try:
                picture = qr.svg_data_uri(link)
            except ValueError:
                problems.append(f"{name}: its link is {len(link.encode())} bytes, too long for a QR code (at most 213): "
                                "use a shorter page address.")
                continue
            try:
                door.update(gor.dt("Code"), name, {"number": number, "link": link, "qr": picture,
                                                   "made_for": gor.made_for(c), "modified": c.get("modified")})
            except TenantError as e:
                if e.kind != STALE:
                    raise
                problems.append(f"{name} was changed a moment ago: press again.")
                continue
            done.append((name, number))
        if not done:
            return gor.message(" ".join(problems) or "No code was made.", "warning")
        made = (f"{done[0][0]}'s code is made (number {done[0][1]})" if len(done) == 1
                else f"{len(done)} codes are made")
        return gor.message(made + ". Print its card from the form's Print menu (Table card). Any earlier code of the "
                           "same record no longer works." + (" " + " ".join(problems) if problems else ""),
                           "warning" if problems else "success")

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.retailer(headers.get(shops.SITE_HEADER) if self.app else self.site)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(gor.verify(ts, sig, raw, s.decode()) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(SUB)
        try:
            body = json.loads(raw)
            names = gor.records_of(body, gor.dt("Code"))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, gor.message(NOT_SET_UP, "warning")
        try:
            return 200, self.make_codes(door, names, site, secrets[0])
        except TenantError as e:
            if e.code in (401, 403):    # the retailer refused the app's user: say so
                return 200, gor.message(REFUSED + (CONNECT_AGAIN if self.app else ""), "warning")
            return 502, {"error": str(e)}

    # ── the guest's page ──
    def guest(self, body: dict) -> tuple[str, object, dict, dict, dict, bytes]:
        """(the site, the door, the code record, the store's row, the code's words, the retailer's current secret) a
        guest's call names, or an answer to give back at once (raised as ``_Answer``)."""
        try:
            site, secrets, door = self.retailer(body.get("s"))
        except Exception:               # noqa: BLE001 — the shops store did not answer
            raise _Answer(503, {"state": "unavailable"}) from None
        found = gor.code_of(site, body.get("t"), secrets) if site else None
        if not found:                   # the same answer for a retailer the app does not know and a bad signature
            raise _Answer(404, {"state": "unknown"})
        if door is None:
            raise _Answer(503, {"state": "unavailable"})
        key = (site, *found)
        kept = self._codes.get(key)
        if kept and self.clock() - kept[0] < CODE_KEEP_S:
            c, row = kept[1], kept[2]
        else:
            c = self.code(door, *found)
            row = self.row(door, c.get("store") or "") if c else None
            with self._lock:
                if len(self._codes) >= MENU_CACHE_MAX * 10:
                    self._codes.clear()
                self._codes[key] = (self.clock(), c, row)
        if c is None:                   # gone, or made again since this card was printed: kept refused, read again later
            raise _Answer(404, {"state": "unknown"})
        table = c.get("kind") == gor.KIND_TABLE
        if not row or not gor.num(row.get("tables_on" if table else "kiosk_on")) or not row.get("register"):
            raise _Answer(200, _say("closed", "ask_staff", ASK_STAFF) if table else
                          _say("closed", "ask_staff_kiosk", ASK_STAFF_KIOSK))
        return site, door, c, row, {"kind": c["kind"], "where": c.get("place_label") or c.get("kiosk_name") or ""}, secrets[0]

    def page_call(self, path: str, raw: bytes) -> tuple[int, dict]:
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("s"), str):
            return 400, {"state": "unknown"}
        try:
            site, door, c, row, where, secret = self.guest(body)
            closed = _say("closed", "ask_staff", ASK_STAFF) if c["kind"] == gor.KIND_TABLE else \
                _say("closed", "ask_staff_kiosk", ASK_STAFF_KIOSK)
            try:
                menu, currency = self.menu(door, site, c["store"], row["register"])
            except gor.Refused:
                return 200, closed
            if path == "/gor/menu":
                return 200, {"state": "open", **where, "menu": menu, "currency": currency,
                             "most_lines": gor.setting(row.get("most_lines"), gor.LINES),
                             "most_qty": gor.setting(row.get("most_qty"), gor.QTY)}
            return self.order(door, site, c, row, menu, body, closed, secret)
        except _Answer as a:
            return a.code, a.body
        except TenantError as e:
            return (404, {"state": "unknown"}) if e.code == 404 else (503, {"state": "unavailable"})

    def order(self, door, site: str, c: dict, row: dict, menu: list, body: dict, closed: dict,
              secret: bytes) -> tuple[int, dict]:
        key = gor.page_key(body.get("key"))
        if not key:
            return 400, {"state": "unknown"}
        try:
            lines = gor.order_lines(body.get("lines"), menu, gor.setting(row.get("most_lines"), gor.LINES),
                                    gor.setting(row.get("most_qty"), gor.QTY),
                                    (row.get("course") or "").strip()[:140] or gor.COURSE)
        except gor.Refused as r:
            return 200, {"state": "refused", "say": "order", "words": r.words}
        try:
            self.space(site, c)
        except Busy:
            return 200, _say("wait", "wait", WAIT)
        store, register, table = c["store"], row["register"], c["kind"] == gor.KIND_TABLE
        try:
            if table:
                place = gor.place_of(door.call("floor_status", query={"store": store}) or {}, c.get("place"))
                if place is None:
                    return 200, closed
                checks = [k for k in place.get("checks") or [] if isinstance(k, dict) and k.get("check")]
                if len(checks) > 1:
                    return 200, _say("refused", "many_bills", MANY_BILLS)
                if checks and checks[0].get("status") == "paying":    # its new lines would sit outside the payment
                    return 200, _say("refused", "paying", PAYING)
                check = checks[0]["check"] if checks else self.open(door, store, register, key, c, place=c["place"])
            else:
                code = gor.kiosk_code(key, secret)
                check = self.open(door, store, register, key, c, label=f"Kiosk {code}")
        except TenantError as e:            # the open: nothing was added; a place switched off since the floor read
            if not e.refused:
                raise
            return 200, closed
        try:
            door.call("check_add_lines", {"check": check, "lines": lines, "key": gor.door_key(key, "add")})
        except TenantError as e:
            if not e.refused:
                raise
            if e.kind == "CheckRequestError":       # a retry whose first send landed on a check since moved or paid
                return 200, _say("refused", "sent_twice", SENT_TWICE)
            if e.kind == "ItemRefusedError":
                return 200, _say("refused", "item_refused", ITEM_REFUSED)
            if e.kind in ("CheckNotOpenError", "CheckChangedError"):
                return 200, _say("refused", "changed", CHANGED)
            return 200, closed                       # the app's set-up (a right, a register, Table Service): staff
        if table:
            return 200, _say("sent", "sent_table", SENT_TABLE)
        return 200, dict(_say("sent", "sent_kiosk", SENT_KIOSK.format(code=code)), code=code)

    def open(self, door, store: str, register: str, key: str, c: dict, place: str = "", label: str = "") -> str:
        req = {"store": store, "pos_profile": register, "key": gor.door_key(key, "open"), "source": gor.SOURCE,
               "source_ref": c["name"]}
        req.update({"place": place} if place else {"label": label, "covers": 1})
        got = door.call("check_open", req)
        if not isinstance(got, dict) or not got.get("check"):
            raise TenantError("check_open -> an answer with no check")
        return got["check"]

    # ── every call ──
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
        if raw is None or len(raw) > gor.BODY_MAX:
            return _json(413, {"error": "too large"})
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return _json(*shops.handle(self.store, self.app, path, headers, raw))
        if path == "/gor/code":
            return _json(*self.press(headers, raw))
        if path in ("/gor/menu", "/gor/order"):
            if len(raw) > gor.PAGE_BODY_MAX:
                return _json(413, {"state": "unknown"})
            return _json(*self.page_call(path, raw))
        return _json(404, {"error": "not found"})


def _say(state: str, say: str, words: str) -> dict:
    """A guest's answer: its state, the id the page translates, and the English words."""
    return {"state": state, "say": say, "words": words}


class _Answer(Exception):
    def __init__(self, code: int, body: dict):
        super().__init__(code)
        self.code, self.body = code, body


def _json(code: int, body: dict) -> tuple[int, bytes, dict]:
    return code, json.dumps(body).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store",
                                             "X-Content-Type-Options": "nosniff"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
    """One call, and one log line (the route, the status and the time; never the body, a link, a code or a key)."""
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
                if n < 0 or n > gor.BODY_MAX:
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
    if not (oneshop.many(conf) or all(oneshop.value(conf, k) for k in ("IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_CODE_SECRET"))):
        raise SystemExit("set IVN_SHOP_URL, IVN_SHOP_KEY and IVN_CODE_SECRET (one retailer), or IVN_LIBRARY_APP with a "
                         "store (many retailers): the app does not start without a way to check a press")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "prefix": gor.PREFIX,
                      "test_modes": "on" if svc.test_modes else "off"}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
