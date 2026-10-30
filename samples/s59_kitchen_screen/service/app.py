#!/usr/bin/env python3
"""S59 — *Kitchen screen*: the service behind the retailer's *Make link* button and the kitchen's screens (standard
library only).

    POST /ksc/link      the retailer's signed press of *Make link* (``desk_action/1``): each ticked screen record gets a
                        new number and its signed link                          →  200 {"message": …, "refresh": true}
    GET  /              the screen's page (its address carries #s=<the retailer's site>&t=<screen>.<number>.<signature>)
    GET  /page.js · /fit.js · /page.css · /ivn-kit.css · /ivn-kit.js   (the kit's own two files, a pinned copy beside the page)
    POST /ksc/board     {"s", "t"}                                     →  200 {"state": "open", "kind", "view", …}
    POST /ksc/move      {"s", "t", "kitchen_order", "ticket", "state"} →  200 {"state": "moved" | "refused", …}
                        {"s", "t", "kitchen_order", "order": true}     (the expo: bump every ready ticket of the order)
    POST /ksc/soldout   {"s", "t", "item_code", "sold_out": bool}      →  200 {"state": "set" | "refused", …}
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below). The
page reads the board every few seconds (the door's own fallback: no socket is held between calls).

**The screen is never trusted with a choice the shop makes.** The page holds no secret. Each call carries the link's
``s`` and ``t``; the service checks ``t``'s signature with the retailer's *Make link* secret before it reads anything,
then reads the screen record (as the app's own user) and refuses a link whose number moved on (a link that leaked and
was made again) or whose screen's kind, store or stations changed. The store and the stations come from the record,
never from the page. A station screen moves only its own stations' tickets, one step; the expo only bumps; the board
moves nothing. Sold out is marked only at the screen's own store, only for a dish on the board or already sold out
there, and only when the store's row allows it (the till's sold-out calls are not fenced to a user's stores).

ONE RETAILER (env or an env file):
    IVN_SHOP_URL, IVN_SHOP_KEY ("<api key>:<api secret>" of the app's user), IVN_LINK_SECRET (handed back at install as
    pp_ksc:sub:link), KSC_PAGE_URL (where this service's page is reached), PORT (8080)
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_ksc), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
KSC_PREFIX (default PP KSC; IVENDNEXT KSC for the library's app)

    python3 service/app.py service/.env.local
"""

from __future__ import annotations

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
import ksc  # noqa: E402
import shops  # noqa: E402

SUB = "link"                         # the manifest's extension_subscriptions[].key
DOOR = "/api/method/ivendnext_mpos.api.v1."     # the till's partner API (its station-ticket door and item availability)
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
BUDGET_S = 7.0                       # a press: the shop waits 10 seconds for it
READ_S = 4.0                         # one read
BOARD_KEEP_S = 1.5                   # a store's board, shared by the screens one copy serves
SOLD_KEEP_S = 30                     # a store's sold-out list
SCREEN_KEEP_S = 15                   # a verified screen and its store's row (a link made again stops within this time)
CACHE_MAX = 2000                     # screens (and stores) one copy keeps
MOVE_GAP_S = 0.25                    # one move (or sold-out tap) a screen this often, per copy
STATIC = {"/": ("page.html", "text/html; charset=utf-8"), "/page.js": ("page.js", "text/javascript; charset=utf-8"),
          "/page.css": ("page.css", "text/css; charset=utf-8"), "/fit.js": ("fit.js", "text/javascript; charset=utf-8"),
          "/ivn-kit.css": ("ivn-kit.css", "text/css; charset=utf-8"),    # the kit's own files, copied beside the page and
          "/ivn-kit.js": ("ivn-kit.js", "text/javascript; charset=utf-8")}   # pinned (kit/design/README.md §1)
ROW_FIELDS = ["parent", "store", "sold_out_on", "warn_min", "late_min", "look", "accent", "language", "tables_on_board",
              "slip_size"]
SET_UP = ("PermissionError", "DeviceRequiredError", "ProfileNotAssignedError", "AssignedProfileDisabledError",
          "DuplicateStoreAssignmentError", "StoreAssignmentIncompleteError")
NOT_SET_UP = ("Kitchen screen is not set up yet: no key from this site has reached it. Ask your manager to check that "
              "the app's user has its key and, if the site could not reach the app, or a key was lost or changed, to "
              "press Connect again on the app.")
REFUSED = ("Kitchen screen may not read or write what it needs. Ask your manager to check the app's user, its role and "
           "its API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way


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
    records, and the till's partner API for the station-ticket door and item availability. Copied from S56's
    ``service/app.py`` (kit ``6bf1024``); a defect here is a defect there."""

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

    def rows(self, doctype: str, fields: list, filters: list, parent: str | None = None, limit: int = 500) -> list:
        q = {"fields": fields, "filters": filters, "limit_page_length": limit}
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


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=time.time, clock=time.monotonic):
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        prefix = (conf.get("KSC_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but KSC_PREFIX is not (IVENDNEXT KSC for the App library's app)")
        ksc.use_prefix(prefix or "PP KSC")
        self.page = (conf.get("KSC_PAGE_URL") or "").strip()
        if not self.page.startswith(("https://", "http://")):
            raise SystemExit("set KSC_PAGE_URL, where screens reach this service's page (each link points there)")
        self.tenants, self.now, self.clock = tenants, now, clock
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            self.site = _host(conf["IVN_SHOP_URL"])
            self.secret = conf["IVN_LINK_SECRET"]
            self.tenant = tenant or tenant_of(conf["IVN_SHOP_URL"], conf["IVN_SHOP_KEY"])
        self.admin = conf.get("PP_ADMIN_TOKEN") or ""
        self.test_modes = os.environ.get("PP_TEST_MODES") == "1" and bool(self.admin)   # environment only
        self.received = []
        self._screens: dict[tuple, tuple] = {}
        self._boards: dict[tuple, tuple] = {}
        self._sold: dict[tuple, tuple] = {}
        self._moved: dict[tuple, float] = {}
        self._lock = threading.Lock()

    def retailer(self, site) -> tuple[str, list[bytes], object | None]:
        """(the retailer's site, the secrets its press and its links may be signed with, newest first, its door: None
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

    def _keep(self, cache: dict, key, value):
        with self._lock:
            if len(cache) >= CACHE_MAX:
                cache.clear()
            cache[key] = (self.clock(), value)

    # ── the screen record and its store's row ──
    def screen(self, door, record: str, number: int | None = None) -> dict | None:
        """The screen record, or None when it is gone or (``number`` given) its number moved on or it changed."""
        try:
            s = door.doc(ksc.dt("Screen"), record)
        except TenantError as e:
            if e.code == 404:
                return None
            raise
        if number is not None and (ksc.num(s.get("number")) != number or s.get("made_for") != ksc.made_for(s)):
            return None                 # made again since, or its kind, store or stations changed since it was made
        return s

    def row(self, door, store: str) -> dict | None:
        rows = door.rows(ksc.dt("Store"), ROW_FIELDS, [["store", "=", store]], parent=ksc.dt("Settings"))
        return rows[0] if rows else None

    # ── the press: Make link ──
    def make_links(self, door, names: list[str], site: str, secret: bytes) -> dict:
        t0, done, problems = self.clock(), [], []
        for name in names:
            if self.clock() - t0 > BUDGET_S - 2:
                problems.append(f"{len(names) - len(done) - len(problems)} more were not made: press again for them.")
                break
            s = self.screen(door, name)
            if s is None:
                problems.append(f"{name} was not found.")
                continue
            if s.get("kind") not in ksc.KINDS or not s.get("store"):
                problems.append(f"{name}: choose its kind and its store, save, then press Make link.")
                continue
            if s["kind"] == ksc.KIND_STATION and not ksc.stations_of(s):
                problems.append(f"{name}: add the screen's kitchen stations, save, then press Make link.")
                continue
            number = ksc.num(s.get("number")) + 1
            link = ksc.link_of(self.page, site, name, number, secret)
            try:
                door.update(ksc.dt("Screen"), name, {"number": number, "link": link, "made_for": ksc.made_for(s),
                                                     "modified": s.get("modified")})
            except TenantError as e:
                if e.kind != STALE:
                    raise
                problems.append(f"{name} was changed a moment ago: press again.")
                continue
            done.append((name, number))
        if not done:
            return ksc.message(" ".join(problems) or "No link was made.", "warning")
        made = (f"{done[0][0]}'s link is made (number {done[0][1]})" if len(done) == 1
                else f"{len(done)} links are made")
        return ksc.message(made + ". Open the link on the screen's browser. Any earlier link of the same screen stops "
                           "working within 15 seconds." + (" " + " ".join(problems) if problems else ""),
                           "warning" if problems else "success")

    def press(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.retailer(headers.get(shops.SITE_HEADER) if self.app else self.site)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(ksc.verify(ts, sig, raw, s.decode()) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            body = json.loads(raw)
            names = ksc.records_of(body, ksc.dt("Screen"))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if self.test_modes:
            self.received = (self.received + [body["context"]])[-20:]
        if door is None:
            return 200, ksc.message(NOT_SET_UP, "warning")
        try:
            return 200, self.make_links(door, names, site, secrets[0])
        except TenantError as e:
            if e.code in (401, 403):    # the retailer refused the app's user: say so
                return 200, ksc.message(REFUSED + (CONNECT_AGAIN if self.app else ""), "warning")
            return 502, {"error": str(e)}

    # ── the screen's calls ──
    def opened(self, body: dict) -> tuple[str, object, dict, dict]:
        """(the site, the door, the screen record, its store's row) a screen's call names, or an answer to give back at
        once (raised as ``_Answer``)."""
        try:
            site, secrets, door = self.retailer(body.get("s"))
        except Exception:               # noqa: BLE001 — the shops store did not answer
            raise _Answer(503, {"state": "unavailable"}) from None
        found = ksc.code_of(site, body.get("t"), secrets) if site else None
        if not found:                   # the same answer for a retailer the app does not know and a bad signature
            raise _Answer(404, {"state": "unknown"})
        if door is None:
            raise _Answer(503, {"state": "unavailable"})
        key = (site, *found)
        kept = self._screens.get(key)
        if kept and self.clock() - kept[0] < SCREEN_KEEP_S:
            s, row = kept[1]
        else:
            s = self.screen(door, *found)
            row = self.row(door, s.get("store") or "") if s else None
            self._keep(self._screens, key, (s, row))
        if s is None:                   # gone, or made again since this link was opened: kept refused, read again later
            raise _Answer(404, {"state": "unknown"})
        if not row:
            raise _Answer(200, {"state": "closed"})
        return site, door, s, row

    def board(self, door, site: str, store: str, fresh: bool = False) -> tuple[list[dict], str]:
        """The store's tickets (cleaned) and the door's ``as_of``, kept ``BOARD_KEEP_S`` seconds per store and copy, so
        the screens one copy serves read the retailer once."""
        key = (site, store)
        kept = self._boards.get(key)
        if not fresh and kept and self.clock() - kept[0] < BOARD_KEEP_S:
            return kept[1]
        got = door.call("station_tickets", query={"store": store}) or {}
        value = (ksc.tickets_of(got), got.get("as_of") if isinstance(got.get("as_of"), str) else "")
        self._keep(self._boards, key, value)
        return value

    def sold(self, door, site: str, store: str) -> list[dict]:
        key = (site, store)
        kept = self._sold.get(key)
        if kept and self.clock() - kept[0] < SOLD_KEEP_S:
            if isinstance(kept[1], tuple):   # refused or late a moment ago: the same answer, kept, so a missing right
                raise TenantError(*kept[1])   # costs 2 calls a minute (a timeout is never told as a 403); a fresh error
            return kept[1]                    # each time, so no request's frames hang on a kept one
        try:
            value = ksc.sold_out_of(door.call("item_availability", query={"warehouse": store}))
        except TenantError as e:
            self._keep(self._sold, key, (str(e), e.code, e.kind))
            raise
        self._keep(self._sold, key, value)
        return value

    def view(self, door, site: str, s: dict, row: dict) -> dict:
        tickets, as_of = self.board(door, site, s["store"])
        kind = s["kind"]
        if kind == ksc.KIND_STATION:
            view = ksc.station_view(tickets, ksc.stations_of(s))
        elif kind == ksc.KIND_EXPO:
            view = ksc.expo_view(tickets)
        else:
            view = ksc.board_view(tickets, bool(ksc.num(row.get("tables_on_board"))))
        out = {"state": "open", "kind": kind, "title": (s.get("title") or "")[:80], "stations": ksc.stations_of(s),
               "look": ksc.look(row), "as_of": as_of, "view": view}
        if kind != ksc.KIND_BOARD and ksc.num(row.get("sold_out_on")):
            try:
                out["sold_out"] = {"dishes": ksc.dishes(self.own(s, tickets)), "out": self.sold(door, site, s["store"])}
            except TenantError:         # the sold-out right missing or the read late: the tickets still show, no button
                pass
        return out

    def own(self, s: dict, tickets: list[dict]) -> list[dict]:
        """The tickets a screen's sold-out list is made from: a station screen's own stations', the expo's every one."""
        return [t for t in tickets if t["station"] in ksc.stations_of(s)] if s["kind"] == ksc.KIND_STATION else tickets

    def spaced(self, site: str, s: dict) -> bool:
        """One move (or sold-out tap) a screen every ``MOVE_GAP_S`` per copy: a flood of taps reads the retailer no more."""
        key, now = (site, s["name"]), self.clock()
        with self._lock:
            if now - self._moved.get(key, -1e9) < MOVE_GAP_S:
                return False
            if len(self._moved) >= CACHE_MAX:
                self._moved.clear()
            self._moved[key] = now
        return True

    def move(self, door, site: str, s: dict, body: dict) -> dict:
        order = body.get("kitchen_order")
        whole = body.get("order") is True
        number, state = body.get("ticket"), body.get("state")
        if not whole and (not isinstance(number, int) or isinstance(number, bool) or state not in ("started", "ready", "bumped")):
            return {"state": "refused", "why": "gone"}
        if whole and s["kind"] != ksc.KIND_EXPO:
            return {"state": "refused", "why": "not_yours"}
        if not self.spaced(site, s):
            return {"state": "refused", "why": "wait"}
        tickets, _ = self.board(door, site, s["store"], fresh=True)      # a move is judged on the board as it is now
        if whole:
            cards = ksc.expo_view([t for t in tickets if t["kitchen_order"] == order])["orders"]
            if not cards or not cards[0]["bump"]:
                return {"state": "refused", "why": "step"}
            todo, state = [t for t in cards[0]["tickets"] if t["state"] == "ready"], "bumped"
        else:
            t = ksc.find(tickets, order, number)
            why = ksc.may_move(s["kind"], ksc.stations_of(s), t, state)
            if why:
                return {"state": "refused", "why": why}
            todo = [t]
        moved = 0
        for t in todo:
            try:
                door.call("station_ticket_move", {"store": s["store"], "kitchen_order": t["kitchen_order"],
                                                  "ticket": t["ticket"], "state": state})
                moved += 1
            except TenantError as e:
                if not e.refused:
                    raise
                with self._lock:
                    self._boards.pop((site, s["store"]), None)
                if e.kind == "TicketStepError":
                    return {"state": "refused", "why": "step"}
                if e.kind == "TicketNotFoundError":
                    return {"state": "refused", "why": "gone"}
                raise
        with self._lock:
            self._boards.pop((site, s["store"]), None)                    # the next read is the board after the move
        return {"state": "moved", "moved": moved}

    def sold_out(self, door, site: str, s: dict, row: dict, body: dict) -> dict:
        code, out = body.get("item_code"), body.get("sold_out")
        if s["kind"] == ksc.KIND_BOARD or not ksc.num(row.get("sold_out_on")):
            return {"state": "refused", "why": "off"}
        if not isinstance(code, str) or not code or len(code) > 140 or not isinstance(out, bool):
            return {"state": "refused", "why": "gone"}
        if not self.spaced(site, s):
            return {"state": "refused", "why": "wait"}
        tickets, _ = self.board(door, site, s["store"])
        listed = {d["item_code"] for d in ksc.dishes(self.own(s, tickets))} | {d["item_code"] for d in self.sold(door, site, s["store"])}
        if code not in listed:          # never an item the kitchen has not seen, never another store's
            return {"state": "refused", "why": "not_listed"}
        door.call("set_item_availability", {"item_code": code, "warehouse": s["store"], "sold_out": 1 if out else 0,
                                            "sold_out_until": ""})
        with self._lock:
            self._sold.pop((site, s["store"]), None)
        return {"state": "set", "item_code": code, "sold_out": out}

    def screen_call(self, path: str, raw: bytes) -> tuple[int, dict]:
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("s"), str):
            return 400, {"state": "unknown"}
        try:
            site, door, s, row = self.opened(body)
            if path == "/ksc/board":
                return 200, self.view(door, site, s, row)
            if path == "/ksc/move":
                return 200, self.move(door, site, s, body)
            return 200, self.sold_out(door, site, s, row, body)
        except _Answer as a:
            return a.code, a.body
        except TenantError as e:
            if e.code == 404:
                return 404, {"state": "unknown"}
            if e.kind in SET_UP or e.code in (401, 403):
                return 200, {"state": "not_set_up"}
            return 503, {"state": "unavailable"}

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
        if raw is None or len(raw) > ksc.BODY_MAX:
            return _json(413, {"error": "too large"})
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return _json(*shops.handle(self.store, self.app, path, headers, raw))
        if path == "/ksc/link":
            return _json(*self.press(headers, raw))
        if path in ("/ksc/board", "/ksc/move", "/ksc/soldout"):
            if len(raw) > ksc.PAGE_BODY_MAX:
                return _json(413, {"state": "unknown"})
            return _json(*self.screen_call(path, raw))
        return _json(404, {"error": "not found"})


class _Answer(Exception):
    def __init__(self, code: int, body: dict):
        super().__init__(code)
        self.code, self.body = code, body


def _json(code: int, body: dict) -> tuple[int, bytes, dict]:
    return code, json.dumps(body).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store",
                                             "X-Content-Type-Options": "nosniff"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
    """One call, and one log line (the route, the status and the time; never the body, a link or a key)."""
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
                if n < 0 or n > ksc.BODY_MAX:
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
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_LINK_SECRET"))):
        raise SystemExit("set IVN_SHOP_URL, IVN_SHOP_KEY and IVN_LINK_SECRET (one retailer), or IVN_LIBRARY_APP with a "
                         "store (many retailers): the app does not start without a way to check a press")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "prefix": ksc.PREFIX,
                      "test_modes": "on" if svc.test_modes else "off"}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
