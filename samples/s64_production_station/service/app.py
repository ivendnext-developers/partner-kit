#!/usr/bin/env python3
"""S64 — *Production station*: the service behind a processing room's station screens and the retailer's two Desk
buttons (standard library only).

    POST /pst/link      the retailer's signed press of *Make link* on a station (``desk_action/1``): a new number and
                        its signed link                                          →  200 {"message": …, "refresh": true}
    POST /pst/work      the retailer's signed press of *Work out* on a production report (``desk_action/1``)
    GET  /              the station's page (its address carries #s=<the retailer's site>&t=<station>.<number>.<signature>)
    GET  /page.js · /code128.js · /page.css · /ivn-kit.css · /ivn-kit.js   (the kit's own two files, pinned beside the page)
    POST /pst/board     {"s", "t"}                                 →  200 {"state": "open", "colour", "workers", …}
    POST /pst/tag       {"s", "t", "worker", "category", "price"}  →  200 {"state": "tagged", "tag": {…}} | refused
    POST /pst/undo      {"s", "t"}                                 →  200 {"state": "undone", "tag": {…}} | refused
    POST /pst/cart      {"s", "t", "warehouse"}                    →  200 {"state": "sent", "cart", "pieces", …} | refused
    GET  /health        200 {"ok": 1}
    POST /ivendnext/connect · /ivendnext/disconnect   many retailers: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below).

**The screen is never trusted with a choice the shop makes.** The page holds no secret. Each call carries the link's
``s`` and ``t``; the service checks ``t``'s signature before it reads anything, then reads the station and its settings
as the app's own user, and refuses a link whose number moved on. The worker, the category and the price a tap names
must be the settings' own: the price written on a tag is the settings' price point, never the page's figure. The colour
comes from the site's own date. Before a price is printed the first time, the engine reads the barcode it made back, and
the tag is refused unless it reads as the same item at the same price.

**Cart full posts stock** (Tier S): a Material Receipt of the cart's tags into the processing room at no value, then a
Material Transfer of the same lines to the place chosen, both naming the cart. Before each entry it looks for a
submitted one naming the cart and takes it, so a second tap or a lost answer never posts twice; a station's unfinished
cart is always the one continued; two calls at once on one cart are told the cart is busy.

ONE RETAILER (env or an env file):
    IVN_SHOP_URL, IVN_SHOP_KEY ("<api key>:<api secret>" of the app's user), IVN_LINK_SECRET and IVN_WORK_SECRET (handed
    back at install as pp_pst:sub:link and pp_pst:sub:work), PST_PAGE_URL (where this service's page is reached), PORT
MANY RETAILERS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 1a):
    IVN_LIBRARY_APP    the App library's id (ivendnext_pst), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
PST_PREFIX (default PP PST; IVENDNEXT PST for the library's app)

    python3 service/app.py service/.env.local

The door (``Tenant``) is S59's (``samples/s59_kitchen_screen/service/app.py``) with S54's ``run_report``: a defect here is
a defect there.
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
import zoneinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLE = os.path.dirname(HERE)
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import oneshop  # noqa: E402
import pst  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

SUBS = {"/pst/link": "link", "/pst/work": "work"}   # the manifest's extension_subscriptions[].key, by route
DOOR = "/api/method/ivendnext_mpos.api.v1."         # the till's partner API (get_count, bulk_update, run_report)
LABEL = "/api/method/ivendnext_pos.api.label_printing.get_item_barcode_for_label"   # the engine's own label encoder
RESOLVE = "/api/method/ivendnext_pos.api.barcode_mask.resolve_barcode"              # the engine's own barcode reader
POS_SALE_REPORT = "POS Sale Report"
STALE = "TimestampMismatchError"     # the shop's refusal of a write whose ``modified`` is not the row's own
TWICE = "DuplicateEntryError"        # the shop's refusal of a second open cart for one station
BUDGET_S = 7.0                       # a press: the shop waits 10 seconds for it
READ_S = 4.0                         # one read
POST_S = 20.0                        # a stock entry's submit (a long cart's lines)
READERS = 8                          # reports at once
STATION_KEEP_S = 15                  # a verified station and its settings (a link made again stops within this time)
ITEM_KEEP_S = 60                     # a category's item of a colour
BARCODE_KEEP_S = 600                 # a barcode the engine read back as its item and price
ZONE_KEEP_S = 3600                   # the site's time zone
SITE_DEFAULT_ZONE = "Asia/Kolkata"   # the zone a site keeps its clock in when its setup never set one (its own default)
LEASE_S = 60                         # a cart written this recently is being posted by another call
CACHE_MAX = 2000
TAGS_MAX = 5000                      # tags one cart, or one read of a report, takes
GROUP_PAGE, RAW_PAGE, RAW_PAGES = 5000, 1000, 20   # a grouped read; else rows read a page at a time
STATIC = {"/": ("page.html", "text/html; charset=utf-8"), "/page.js": ("page.js", "text/javascript; charset=utf-8"),
          "/code128.js": ("code128.js", "text/javascript; charset=utf-8"),
          "/page.css": ("page.css", "text/css; charset=utf-8"),
          "/ivn-kit.css": ("ivn-kit.css", "text/css; charset=utf-8"),    # the kit's own files, copied beside the page and
          "/ivn-kit.js": ("ivn-kit.js", "text/javascript; charset=utf-8")}   # pinned (kit/design/README.md §1)
SET_UP = ("PermissionError", "DeviceRequiredError")
NOT_SET_UP = ("Production station is not set up yet: no key from this site has reached it. Ask your manager to check "
              "that the app's user has its key and, if the site could not reach the app, or a key was lost or changed, "
              "to press Connect again on the app.")
REFUSED = ("Production station may not read or write what it needs. Ask your manager to check the app's user, its role "
           "and its API key.")
CONNECT_AGAIN = " Then press Connect again on the app."    # many retailers: a new key reaches the service only that way
LATE = "The tags took the press's time, so nothing was written. Name fewer days and press again."
REPORT_REFUSED = ("Production station could not run POS Sale Report: check that the app's role is on it (the install "
                  "adds it; see Role Permission for Page and Report) and that each store still exists.")


class TenantError(Exception):
    def __init__(self, msg: str, code: int | None = None, kind: str = ""):
        super().__init__(msg)
        self.code = code            # the retailer's HTTP status, when it answered one
        self.kind = kind            # the retailer's error type (exc_type), never its message

    @property
    def refused(self) -> bool:
        """The retailer answered and refused: nothing was written (never a lost answer or a fault of the shop's)."""
        return self.code is not None and 400 <= self.code < 500


class ReportRefused(TenantError):
    """A report refused the app's user: 417 (a right missing on a filter's record type) or 403 (the role not on it)."""


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
    """The service's only door into iVendNext, as the app's own user (token key:secret): the record API, the till's
    partner API and the engine's label encoder and barcode reader."""

    def __init__(self, base: str, key: str, secret: str, timeout: float = READ_S):
        self.base, self.timeout, self._auth = base.rstrip("/"), timeout, f"token {key}:{secret}"

    def _open(self, method: str, url: str, body: bytes | None, what: str, ctype: str = "application/json",
              timeout: float | None = None):
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

    def _data(self, method: str, path: str, body: dict | None = None, query: dict | None = None, kind=dict,
              timeout: float | None = None):
        url = f"{self.base}/api/resource/" + "/".join(urllib.parse.quote(p, safe="") for p in path.split("/", 1))
        if query:
            url += "?" + urllib.parse.urlencode({k: json.dumps(v) if not isinstance(v, (str, int)) else v
                                                 for k, v in query.items()})
        what = path.split("/")[0]
        raw = json.dumps(body).encode() if body is not None else None
        try:
            data = self._open(method, url, raw, what, timeout=timeout)["data"]
        except (KeyError, TypeError):
            raise TenantError(f"{method} {what} -> an answer with no data") from None
        if not isinstance(data, kind):
            raise TenantError(f"{method} {what} -> an answer with no data")
        return data

    def doc(self, doctype: str, name: str) -> dict:
        return self._data("GET", f"{doctype}/{name}")

    def rows(self, doctype: str, fields: list, filters: list, limit: int = 500, start: int = 0, order_by: str = "",
             group_by: str = "") -> list:
        q = {"fields": fields, "filters": filters, "limit_page_length": limit}
        if start:
            q["limit_start"] = start
        if order_by:
            q["order_by"] = order_by
        if group_by:
            q["group_by"] = group_by
        return [r for r in self._data("GET", doctype, query=q, kind=list) if isinstance(r, dict)]

    def insert(self, doctype: str, body: dict, timeout: float | None = None) -> dict:
        return self._data("POST", doctype, body, timeout=timeout)

    def update(self, doctype: str, name: str, body: dict) -> dict:
        return self._data("PUT", f"{doctype}/{name}", body)

    def call(self, verb: str, body: dict | None = None, query: dict | None = None, timeout: float | None = None):
        """One of the till's partner calls; its answer (``message``)."""
        url = self.base + DOOR + verb + ("?" + urllib.parse.urlencode(query) if query else "")
        raw = json.dumps(body).encode() if body is not None else None
        out = self._open("POST" if body is not None else "GET", url, raw, verb, timeout=timeout)
        return out.get("message") if isinstance(out, dict) else None

    def engine(self, path: str, query: dict):
        """One of the engine's own label calls (``LABEL``, ``RESOLVE``); its answer (``message``)."""
        out = self._open("GET", self.base + path + "?" + urllib.parse.urlencode(query), None, path.rsplit(".", 1)[-1])
        return out.get("message") if isinstance(out, dict) else None

    def report(self, name: str, filters: dict, timeout: float | None = None) -> dict:
        """``run_report``: the report's columns and rows, as the app's user reads them."""
        body = urllib.parse.urlencode({"report_name": name, "filters": json.dumps(filters)}).encode()
        try:
            return self._open("POST", self.base + DOOR + "run_report", body, name, "application/x-www-form-urlencoded",
                              timeout)
        except TenantError as e:
            if e.code in (403, 417):
                raise ReportRefused(f"POST {name} -> HTTP {e.code}", e.code) from None
            raise


def tenant_of(url: str, key: str) -> Tenant:
    """A retailer's door from the key the retailer's site handed over ("<api key>:<api secret>")."""
    api_key, _, api_secret = key.partition(":")
    return Tenant(url, api_key, api_secret)


def _host(url: str) -> str:
    return (urllib.parse.urlsplit(url).netloc or "").lower()


def user_key(record: dict | None) -> str | None:
    """The key ("<api key>:<api secret>") of the app's own user the retailer's site handed over, or None."""
    secrets = (record or {}).get("secrets") or {}
    users = sorted(k for k in secrets if k.startswith("user:"))
    return secrets[users[0]] if users else None


class _Answer(Exception):
    def __init__(self, code: int, body: dict):
        super().__init__(code)
        self.code, self.body = code, body


def _refused(why: str, **more) -> dict:
    return dict({"state": "refused", "why": why}, **more)


class Service:
    def __init__(self, conf: dict, tenant=None, store=None, tenants=tenant_of, now=time.time, clock=time.monotonic):
        self.app = oneshop.value(conf, oneshop.MANY)
        prefix = (conf.get("PST_PREFIX") or "").strip()
        if self.app and not prefix:      # the library's record types are not the sample's: every read would 404
            raise SystemExit("IVN_LIBRARY_APP is set but PST_PREFIX is not (IVENDNEXT PST for the App library's app)")
        pst.use_prefix(prefix or "PP PST")
        self.page = (conf.get("PST_PAGE_URL") or "").strip()
        if not self.page.startswith(("https://", "http://")):
            raise SystemExit("set PST_PAGE_URL, where stations reach this service's page (each link points there)")
        self.tenants, self.now, self.clock = tenants, now, clock
        if self.app:                                    # many retailers: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one retailer, from the settings
            one = oneshop.settings(conf, ["IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_LINK_SECRET", "IVN_WORK_SECRET"])
            self.site = _host(one["IVN_SHOP_URL"])
            self.secrets = {"link": one["IVN_LINK_SECRET"], "work": one["IVN_WORK_SECRET"]}
            self.tenant = tenant or tenant_of(one["IVN_SHOP_URL"], one["IVN_SHOP_KEY"])
        self._stations: dict = {}
        self._items: dict = {}
        self._barcodes: dict = {}
        self._zones: dict = {}
        self._lock = threading.Lock()
        self.last_read = ""             # how the last report read the tags: "grouped" or "pages" (the log says it)

    def retailer(self, site, sub: str) -> tuple[str, list[bytes], object | None]:
        """(the retailer's site, the secrets ``sub``'s press and the links may be signed with, newest first, its door:
        None until it handed over a user's key). A site the service does not know has no secrets."""
        if not self.app:
            return (self.site, [self.secrets[sub].encode()], self.tenant) if site == self.site else ("", [], None)
        site = shops.site_of(site)
        record = self.store.get(site) if site else None
        secrets = shops.secrets_for(record, f"{self.app}:sub:{sub}")
        key = user_key(record)
        door = self.tenants(record["url"], key) if key else None
        return site or "", secrets, door

    def _kept(self, cache: dict, key, most: float):
        kept = cache.get(key)
        return kept[1] if kept and self.clock() - kept[0] < most else None

    def _keep(self, cache: dict, key, value):
        with self._lock:
            if len(cache) >= CACHE_MAX:
                cache.clear()
            cache[key] = (self.clock(), value)

    # ── the site's own day ──
    def site_now(self, door, site: str) -> datetime.datetime:
        """The site's own date and hour, from its time zone (System Settings, which the install lets the app's role
        read; blank, the site's own default zone); read once an hour."""
        zone = self._kept(self._zones, site, ZONE_KEEP_S)
        if zone is None:
            name = (door.doc("System Settings", "System Settings") or {}).get("time_zone") or SITE_DEFAULT_ZONE
            try:
                zone = zoneinfo.ZoneInfo(name)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                zone = datetime.timezone.utc
            self._keep(self._zones, site, zone)
        return datetime.datetime.fromtimestamp(self.now(), zone)

    # ── the presses ──
    def press(self, sub: str, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, secrets, door = self.retailer(headers.get(shops.SITE_HEADER) if self.app else self.site, sub)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(pst.verify(ts, sig, raw, s.decode(), self.now()) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(sub)
        try:
            body = json.loads(raw)
            names = pst.records_of(body, pst.dt("Station" if sub == "link" else "Report"), 50 if sub == "link" else 1)
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if door is None:
            return 200, pst.message(NOT_SET_UP, "warning")
        try:
            if sub == "link":
                return 200, self.make_links(door, names, site, secrets[0])
            return 200, self.work(door, site, names[0])
        except ReportRefused:
            return 200, pst.message(REPORT_REFUSED, "warning")
        except TenantError as e:
            if e.code in (401, 403):    # the retailer refused the app's user: say so
                return 200, pst.message(REFUSED + (CONNECT_AGAIN if self.app else ""), "warning")
            if e.code == 404:
                return 200, pst.message(f"{names[0]} or its settings were not found.", "warning")
            if str(e).endswith("ran out of time"):
                return 200, pst.message(LATE, "warning")
            return 502, {"error": str(e)}

    def make_links(self, door, names: list[str], site: str, secret: bytes) -> dict:
        t0, done, problems = self.clock(), [], []
        for name in names:
            if self.clock() - t0 > BUDGET_S - 2:
                problems.append(f"{len(names) - len(done) - len(problems)} more were not made: press again for them.")
                break
            try:
                s = door.doc(pst.dt("Station"), name)
            except TenantError as e:
                if e.code != 404:
                    raise
                problems.append(f"{name} was not found.")
                continue
            if not s.get("settings"):
                problems.append(f"{name}: choose its settings, save, then press Make link.")
                continue
            number = pst.num(s.get("number")) + 1
            link = pst.link_of(self.page, site, name, number, secret)
            try:
                door.update(pst.dt("Station"), name, {"number": number, "link": link, "made_for": pst.made_for(s),
                                                      "modified": s.get("modified")})
            except TenantError as e:
                if e.kind != STALE:
                    raise
                problems.append(f"{name} was changed a moment ago: press again.")
                continue
            done.append((name, number))
        if not done:
            return pst.message(" ".join(problems) or "No link was made.", "warning")
        made = (f"{done[0][0]}'s link is made (number {done[0][1]})" if len(done) == 1
                else f"{len(done)} links are made")
        return pst.message(made + ". Open the link on the station's browser. Any earlier link of the same station stops "
                           "working within 15 seconds." + (" " + " ".join(problems) if problems else ""),
                           "warning" if problems else "success")

    # ── the station's calls ──
    def opened(self, body: dict) -> tuple[str, object, dict, dict]:
        """(the site, the door, the station record, its settings) a station's call names, or an answer to give back at
        once (raised as ``_Answer``)."""
        try:
            site, secrets, door = self.retailer(body.get("s"), "link")
        except Exception:               # noqa: BLE001 — the shops store did not answer
            raise _Answer(503, {"state": "unavailable"}) from None
        found = pst.code_of(site, body.get("t"), secrets) if site else None
        if not found:                   # the same answer for a retailer the app does not know and a bad signature
            raise _Answer(404, {"state": "unknown"})
        if door is None:
            raise _Answer(503, {"state": "unavailable"})
        key = (site, *found)
        kept = self._kept(self._stations, key, STATION_KEEP_S)
        if kept is None:
            try:
                s = door.doc(pst.dt("Station"), found[0])
            except TenantError as e:
                if e.code != 404:
                    raise
                s = None
            if s is not None and (pst.num(s.get("number")) != found[1] or s.get("made_for") != pst.made_for(s)):
                s = None                # made again since, or moved to other settings since it was made
            settings = door.doc(pst.dt("Settings"), s["settings"]) if s else None
            kept = (s, settings)
            self._keep(self._stations, key, kept)
        s, settings = kept
        if s is None:
            raise _Answer(404, {"state": "unknown"})
        return site, door, s, settings

    def unsent(self, station: str) -> list:
        return [["station", "=", station], ["cart", "is", "not set"], ["void", "=", 0]]

    def board(self, door, site: str, s: dict, settings: dict) -> dict:
        today = self.site_now(door, site).date()
        colour = pst.colour_of(settings, today)
        points = pst.price_points(settings)
        count = door.call("get_count", query={"doctype": pst.dt("Tag"), "filters": json.dumps(self.unsent(s["name"]))})
        one_day = bool(colour) and colour[1] == today and pst.day_of(settings.get("day_colour_on")) == today \
            and pst.text(settings.get("day_colour"), 40) == colour[0]       # the lead's colour for today alone
        return {"state": "open", "title": (s.get("title") or s["name"])[:80], "colour": colour[0] if colour else "",
                "one_day": one_day,
                "workers": pst.workers(settings), "categories": [{"name": c, "prices": p} for c, p in points.items()],
                "places": pst.places(settings), "cart": pst.num(count), "tag": pst.tag_size(settings),
                "currency": pst.text(settings.get("currency"), 3)}

    def item(self, door, site: str, category: str, colour: str) -> dict | None:
        key = (site, category, colour.lower())
        kept = self._kept(self._items, key, ITEM_KEEP_S)
        if kept is None:
            rows = door.rows("Item", ["name", pst.FIELD_COLOUR, "custom_barcode_mask", "barcodes.barcode as barcode"],
                             [["item_group", "=", category], [pst.FIELD_COLOUR, "=", colour], ["disabled", "=", 0]],
                             limit=100)
            kept = (pst.item_for(rows, colour),)
            self._keep(self._items, key, kept)
        return kept[0]

    def barcode(self, door, site: str, item: dict, price: float) -> tuple[str, str]:
        """(the tag's barcode, "") or ("", why not): the engine's own encoder, read back by the engine's own reader as
        the same item at the same price before it is printed the first time."""
        key = (site, item["name"], price)
        kept = self._kept(self._barcodes, key, BARCODE_KEEP_S)
        if kept:
            return kept, ""
        code = door.engine(LABEL, {"item_code": item["name"], "price": f"{price:.2f}"})
        if not isinstance(code, str) or not code.strip():
            return "", "no_label"
        resolved = door.engine(RESOLVE, {"barcode": code})
        if not pst.read_back(resolved, item, price):
            return "", "too_old"
        self._keep(self._barcodes, key, code)
        return code, ""

    def tag(self, door, site: str, s: dict, settings: dict, body: dict) -> dict:
        worker, category = pst.text(body.get("worker"), 80), pst.text(body.get("category"))
        if worker not in pst.workers(settings):
            return _refused("no_worker")
        price = pst.price_of(pst.price_points(settings), category, body.get("price"))
        if price is None:
            return _refused("no_price")
        now = self.site_now(door, site)
        colour = pst.colour_of(settings, now.date())
        if not colour:
            return _refused("no_colour")
        item = self.item(door, site, category, colour[0])
        if item is None:
            return _refused("no_item", colour=colour[0], category=category)
        if not item["mask"]:
            return _refused("no_mask", item=item["name"])
        code, why = self.barcode(door, site, item, price)
        if why:
            return _refused(why, item=item["name"])
        row = door.insert(pst.dt("Tag"), {"station": s["name"], "worker": worker, "category": category,
                                          "item": item["name"], "colour": colour[0], "week_start": colour[1].isoformat(),
                                          "price": price, "quantity": 1, "barcode": code,
                                          "tagged_on": now.date().isoformat(), "hour": now.hour, "void": 0})
        return {"state": "tagged", "tag": {"name": row.get("name"), "price": price, "category": category,
                                           "colour": colour[0], "barcode": code}}

    def undo(self, door, s: dict) -> dict:
        rows = door.rows(pst.dt("Tag"), ["name", "price", "category", "colour"], self.unsent(s["name"]), limit=1,
                         order_by="creation desc")
        if not rows:
            return _refused("no_undo")
        door.update(pst.dt("Tag"), rows[0]["name"], {"void": 1})
        r = rows[0]
        return {"state": "undone", "tag": {"name": r["name"], "price": r.get("price"), "category": r.get("category"),
                                           "colour": r.get("colour")}}

    # ── Cart full: the stock (Tier S) ──
    def _posted(self, door, cart: str, purpose: str) -> str | None:
        """A submitted stock entry of ``purpose`` that already names the cart (a lost answer's, a second tap's)."""
        got = door.rows("Stock Entry", ["name"], [[pst.FIELD_CART, "=", cart], ["purpose", "=", purpose],
                                                  ["docstatus", "=", 1]], limit=1, order_by="creation asc")
        return got[0]["name"] if got else None

    def _written(self, door, cart: str, body: dict) -> dict | None:
        """The cart written with its own ``modified``: None when another call wrote it since (that call is posting it)."""
        try:
            return door.update(pst.dt("Cart"), cart, body)
        except TenantError as e:
            if e.kind == STALE:
                return None
            raise

    def _fresh(self, door, site: str, cart: dict) -> bool:
        """Whether the cart was written in the last ``LEASE_S`` seconds: a call is posting it now (or one died a moment
        ago), so this one waits. The site writes ``modified`` in its own time."""
        try:
            at = datetime.datetime.fromisoformat(pst.text(cart.get("modified"), 40))
        except ValueError:
            return False
        now = self.site_now(door, site).replace(tzinfo=None)
        return abs((now - at).total_seconds()) < LEASE_S

    def cart(self, door, site: str, s: dict, settings: dict, body: dict) -> dict:
        room, company = pst.text(settings.get("room")), pst.text(settings.get("company"))
        named = {p["warehouse"]: p["label"] for p in pst.places(settings)}
        if not room or not company:
            return _refused("no_room")
        carts = door.rows(pst.dt("Cart"), ["name", "state", "destination", "modified"], [["station", "=", s["name"]]],
                          limit=20, order_by="creation desc")
        mine = [c for c in carts if not pst.finished(c, room)]
        if mine:                        # a station's unfinished cart is continued, never a second one
            if self._fresh(door, site, mine[-1]):
                return {"state": "busy"}
            cart = self._written(door, mine[-1]["name"], {"modified": mine[-1]["modified"]})   # this call holds it now
            if cart is None:
                return {"state": "busy"}
        else:
            to = pst.text(body.get("warehouse"))
            if to not in named:
                return _refused("no_place")
            if not pst.num(door.call("get_count", query={"doctype": pst.dt("Tag"),
                                                          "filters": json.dumps(self.unsent(s["name"]))})):
                if carts and self._fresh(door, site, carts[0]) and pst.finished(carts[0], room):
                    cart = door.doc(pst.dt("Cart"), carts[0]["name"])    # a second tap of a cart just sent: its answer
                    return self._answer(cart, named, room)
                return _refused("empty")
            try:
                cart = door.insert(pst.dt("Cart"), {"station": s["name"], "destination": to, "state": "Open",
                                                    "closed_on": self.site_now(door, site).date().isoformat(),
                                                    "pieces": 0, "open_for": s["name"]})
            except TenantError as e:
                if e.kind == TWICE:     # another tap made this station's cart a moment ago: it is posting now
                    return {"state": "busy"}
                raise
        if cart.get("state") == "Open":
            cart = self._receive(door, s, cart, room, company)
            if "name" not in cart:
                return cart
        if cart.get("state") == "Received" and cart.get("destination") != room:
            cart = self._send(door, cart, room, company)
            if "name" not in cart:
                return cart
        return self._answer(cart, named, room)

    def _answer(self, cart: dict, named: dict, room: str) -> dict:
        to = cart.get("destination") or ""
        return {"state": "sent", "cart": cart["name"], "pieces": pst.num(cart.get("pieces")), "place": named.get(to, to),
                "kept": to == room, "receipt": cart.get("receipt") or "", "transfer": cart.get("transfer") or ""}

    def _receive(self, door, s: dict, cart: dict, room: str, company: str) -> dict:
        """The cart's tags stamped with it, then its one Material Receipt into the processing room at no value. A receipt
        already naming the cart (an earlier call's answer was lost) is taken, and no tag is added to the cart."""
        name = cart["name"]
        se = self._posted(door, name, "Material Receipt")
        if se:
            pieces = sum(pst.num(r.get("qty")) for r in door.doc("Stock Entry", se).get("items") or [])
        else:
            todo = door.rows(pst.dt("Tag"), ["name"], self.unsent(s["name"]), limit=TAGS_MAX)
            for i in range(0, len(todo), 500):
                docs = [{"doctype": pst.dt("Tag"), "docname": t["name"], "cart": name} for t in todo[i:i + 500]]
                got = door.call("bulk_update", {"docs": json.dumps(docs)}, timeout=POST_S)
                if (got or {}).get("failed_docs"):
                    raise TenantError(f"bulk_update -> {len(got['failed_docs'])} tags not stamped")
            tags = door.rows(pst.dt("Tag"), ["item", "quantity", "void"], [["cart", "=", name]], limit=TAGS_MAX)
            lines = pst.cart_lines(tags)
            if not lines:
                return _refused("empty")
            uoms = {r["name"]: r.get("stock_uom") for r in door.rows("Item", ["name", "stock_uom"],
                                                                     [["name", "in", [i for i, _ in lines]]],
                                                                     limit=TAGS_MAX)}
            if any(not uoms.get(i) for i, _ in lines):
                raise TenantError("Item -> a cart's item has no stock unit")
            se = door.insert("Stock Entry", pst.receipt(company, room, name, lines, uoms), timeout=POST_S)["name"]
            pieces = sum(q for _, q in lines)
        done = {"state": "Received", "receipt": se, "pieces": pieces, "modified": cart.get("modified")}
        if cart.get("destination") == room:
            done["open_for"] = None     # kept in the room: the cart is done, and the station may start another
        return self._written(door, name, done) or {"state": "busy"}

    def _send(self, door, cart: dict, room: str, company: str) -> dict:
        """The receipt's own lines moved from the processing room to the cart's place: its one Material Transfer."""
        name = cart["name"]
        se = self._posted(door, name, "Material Transfer")
        if not se:
            items = door.doc("Stock Entry", cart["receipt"]).get("items") or []
            lines = [(r["item_code"], r["qty"]) for r in items]
            uoms = {r["item_code"]: r.get("stock_uom") or r.get("uom") for r in items}
            se = door.insert("Stock Entry", pst.transfer(company, room, cart["destination"], name, lines, uoms),
                             timeout=POST_S)["name"]
        return self._written(door, name, {"state": "Sent", "transfer": se, "open_for": None,
                                          "modified": cart.get("modified")}) or {"state": "busy"}

    # ── Work out (S54's shape) ──
    def left(self, t0: float) -> float:
        rest = BUDGET_S - (self.clock() - t0)
        if rest <= 0:
            raise TenantError("the press ran out of time")
        return min(READ_S, rest)

    def groups(self, door, keys: list, filters: list, t0: float) -> list:
        """The non-void tags' pieces by ``keys``: one grouped read where the record API allows it, else every row a page
        at a time (``last_read`` says which)."""
        try:
            got = door.rows(pst.dt("Tag"), keys + ["sum(quantity) as pieces"], filters, limit=GROUP_PAGE,
                            group_by=", ".join(keys))
            if all("pieces" in r for r in got) and len(got) < GROUP_PAGE:
                self.last_read = "grouped"
                return got
        except TenantError as e:
            if not e.refused or e.code in (401, 403):
                raise
        rows: list = []
        for page in range(RAW_PAGES):
            self.left(t0)
            got = door.rows(pst.dt("Tag"), keys + ["quantity"], filters, limit=RAW_PAGE, start=page * RAW_PAGE,
                            order_by="name asc")
            rows += got
            if len(got) < RAW_PAGE:
                break
        else:
            raise TenantError("the press ran out of time")   # more tags than one press reads
        self.last_read = "pages"
        out: dict = {}
        for r in rows:
            k = tuple(r.get(x) for x in keys)
            out[k] = out.get(k, 0) + pst.num(r.get("quantity"))
        return [dict(zip(keys, k), pieces=v) for k, v in out.items()]

    def work(self, door, site: str, name: str) -> dict:
        t0 = self.clock()
        doc = door.doc(pst.dt("Report"), name)
        frm, to = pst.day_of(doc.get("from_date")), pst.day_of(doc.get("to_date"))
        if frm is None or to is None or frm > to:
            return pst.message(f"{name}: fill From and To (From first), then press again.", "warning")
        if (to - frm).days >= pst.DAYS_MAX:
            return pst.message(f"{name}: at most {pst.DAYS_MAX} days a report; make a second one for the rest.", "warning")
        which = pst.text(doc.get("settings"))
        if not which:
            some = door.rows(pst.dt("Settings"), ["name"], [], limit=2)
            if len(some) != 1:
                return pst.message(f"{name}: choose the settings (the company) to read, then press again.", "warning")
            which = some[0]["name"]
        settings = door.doc(pst.dt("Settings"), which)
        stations = [r["name"] for r in door.rows(pst.dt("Station"), ["name"], [["settings", "=", which]], limit=500)]
        today = self.site_now(door, site).date()
        weeks = pst.weeks_between(settings, frm, to)
        rows, crows = [], []
        if stations:
            groups = self.groups(door, ["tagged_on", "station", "worker", "hour"],
                                 [["station", "in", stations], ["void", "=", 0], ["tagged_on", ">=", frm.isoformat()],
                                  ["tagged_on", "<=", to.isoformat()]], t0)
            rows = pst.worker_rows(groups)
        if weeks:
            tagged: dict = {}
            if stations:
                for g in self.groups(door, ["colour", "week_start"],
                                     [["station", "in", stations], ["void", "=", 0],
                                      ["week_start", "in", sorted({w.isoformat() for _, w in weeks})]], t0):
                    k = (pst.text(g.get("colour"), 40), pst.text(g.get("week_start"))[:10])
                    tagged[k] = tagged.get(k, 0) + pst.num(g.get("pieces"))
            crows = pst.colour_rows(weeks, tagged, self.sold(door, settings, weeks, today, t0))
        self.left(t0)
        summary = pst.summary_of(rows, crows, frm, to)
        door.update(pst.dt("Report"), name, {"worker_rows": rows, "colour_rows": crows, "summary": summary})
        return pst.message(f"{len(rows)} worker row{'' if len(rows) == 1 else 's'} and {len(crows)} colour "
                           f"row{'' if len(crows) == 1 else 's'} written. " + summary)

    def sold(self, door, settings: dict, weeks: list, today: datetime.date, t0: float) -> dict:
        """{(colour, week start): units the till sold of that colour's items in the week's window}, across the places a
        cart can go that are stores, from the retailer's own POS Sale Report."""
        cats = list(pst.price_points(settings))
        names = sorted({c for c, _ in weeks})
        here = [p["warehouse"] for p in pst.places(settings)]
        if not cats or not here:
            return {}
        items = door.rows("Item", ["name", pst.FIELD_COLOUR], [[pst.FIELD_COLOUR, "in", names],
                                                               ["item_group", "in", cats]], limit=TAGS_MAX)
        colour_of = {r["name"]: pst.text(r.get(pst.FIELD_COLOUR), 40).lower() for r in items}
        stores = [r["name"] for r in door.rows("Warehouse", ["name"], [["name", "in", here],
                                                                      ["custom_is_retail_store", "=", 1]], limit=500)]
        n = len(pst.colours(settings))
        windows = {(c, w.isoformat()): pst.sold_window(w, n, today) for c, w in weeks}
        ranges = sorted({r for r in windows.values() if r[0] <= r[1]})
        calls = [(r, st) for r in ranges for st in stores]
        if not calls:
            return {}
        pos = {"report_type": "Item", "pos": "", "item_group": "", "item_code": "", "customer": "", "customer_group": ""}

        def one(c):
            (a, b), st = c
            return door.report(POS_SALE_REPORT, dict(pos, warehouse=st, from_date=a.isoformat(), to_date=b.isoformat()),
                               timeout=self.left(t0))
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(READERS, len(calls))) as pool:
            answers = list(pool.map(one, calls))
        by_range: dict = {}
        for (rng, _), answer in zip(calls, answers):
            per = by_range.setdefault(rng, {})
            for item, q in sold_of(answer).items():
                per[item] = per.get(item, 0.0) + q
        out = {}
        for (colour, start), rng in windows.items():
            per = by_range.get(rng, {})
            out[(colour, start)] = sum(q for item, q in per.items() if colour_of.get(item) == colour.lower())
        return out

    def station_call(self, path: str, raw: bytes) -> tuple[int, dict]:
        try:
            body = json.loads(raw)
        except ValueError:
            body = None
        if not isinstance(body, dict) or not isinstance(body.get("s"), str):
            return 400, {"state": "unknown"}
        try:
            site, door, s, settings = self.opened(body)
            if path == "/pst/board":
                return 200, self.board(door, site, s, settings)
            if path == "/pst/tag":
                return 200, self.tag(door, site, s, settings, body)
            if path == "/pst/undo":
                return 200, self.undo(door, s)
            return 200, self.cart(door, site, s, settings, body)
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

    def handle(self, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
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
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return _json(*shops.handle(self.store, self.app, path, headers, raw))
        if path in SUBS:
            return _json(*self.press(SUBS[path], headers, raw))
        if path in ("/pst/board", "/pst/tag", "/pst/undo", "/pst/cart"):
            return _json(*self.station_call(path, raw))
        return _json(404, {"error": "not found"})


def _key(c) -> str:
    """A report column's name: its fieldname (``run_report`` answers every column as a dict), else its label."""
    if isinstance(c, dict):
        c = c.get("fieldname") or c.get("label") or ""
    return c.strip().lower().replace(" ", "_") if isinstance(c, str) else ""


def sold_of(answer) -> dict:
    """{item: units sold, returns taken off} from POS Sale Report's answer (report type Item: ``item``, ``unit_solds``),
    whether it answered its rows as lists or as dicts (S54's reading)."""
    msg = answer.get("message") if isinstance(answer, dict) and "message" in answer else answer
    if isinstance(msg, dict) and msg.get("prepared_report"):
        raise ReportRefused("POS Sale Report was made a prepared report", 417)
    if not isinstance(msg, dict) or not isinstance(msg.get("result"), list):
        raise TenantError("POS Sale Report answered no rows")
    cols = [_key(c) for c in msg.get("columns") or []]
    out: dict = {}
    for r in msg["result"]:
        row = {_key(k): v for k, v in r.items()} if isinstance(r, dict) else dict(zip(cols, r)) if isinstance(r, (list, tuple)) else {}
        item = row.get("item")
        if isinstance(item, str):
            try:
                out[item] = out.get(item, 0.0) + float(row.get("unit_solds") or 0)
            except (TypeError, ValueError):
                pass
    return out


def _json(code: int, body: dict) -> tuple[int, bytes, dict]:
    return code, json.dumps(body).encode(), {"Content-Type": "application/json", "Cache-Control": "no-store",
                                             "X-Content-Type-Options": "nosniff"}


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, bytes, dict]:
    """One call, and one log line (the route, the status and the time; never the body, a link or a key)."""
    t0 = time.monotonic()
    code, body, hdrs = svc.handle(method, path, headers, raw)
    line = {"request": (headers.get("X-iVendNext-Request-Id") or "-")[:40], "route": path.split("?", 1)[0][:20],
            "status": code, "ms": int((time.monotonic() - t0) * 1000)}
    if path.startswith("/pst/work") and svc.last_read:
        line["tags_read"] = svc.last_read
    print(json.dumps(line), flush=True)
    return code, body, hdrs


def make_server(svc: Service, port: int):
    class Handler(BaseHTTPRequestHandler):
        timeout = 30

        def _answer(self, method: str):
            raw = None
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(min(n, 64 * 1024))
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
    """As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 1a). The template's ``function``
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
    one = ("IVN_SHOP_URL", "IVN_SHOP_KEY", "IVN_LINK_SECRET", "IVN_WORK_SECRET")
    if not (oneshop.many(conf) or all(oneshop.value(conf, k) for k in one)):
        raise SystemExit("set IVN_SHOP_URL, IVN_SHOP_KEY, IVN_LINK_SECRET and IVN_WORK_SECRET (one retailer), or "
                         "IVN_LIBRARY_APP with a store (many retailers): the app does not start without a way to check a press")
    svc = Service(conf)
    srv = make_server(svc, int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1], "prefix": pst.PREFIX}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
