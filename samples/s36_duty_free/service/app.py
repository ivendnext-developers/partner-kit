#!/usr/bin/env python3
"""S36 — *Duty-free allowance and boarding pass*: the service behind the shop's check before payment (standard library
only).

    POST /dfa/check   the shop's signed check (``check/1``)   →  200 {"verdict": "allow" | "refuse", ...}
    GET  /health      200 {"status": "ok"}
    POST /ivendnext/connect · /ivendnext/disconnect   many shops: the app template's handshake (shops.py)

On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below): it only
answers presses.

The call is checked with the secret the install made for the check, ``<app>:sub:allowance``. A sale that sells nothing (a
refund) is allowed at once, and a sale with no boarding pass is refused, both without reading the shop. Otherwise the
shop's settings (``<prefix> Settings``, the record ``Default``) and its item groups (with their allowance fields) are read
with the app's integration key and kept one minute (``KEPT_TTL``). The pass is judged (``dutyfree.pass_problem``); then, if
the sale holds an item of a limited group, the basket's items are read (their stock unit and *Counts toward the allowance
as*), and the passenger's earlier sales on the same pass: the submitted POS Invoices whose sale detail starts with the
pass's first 60 characters (at most ``EARLIER_MAX``), each read for its lines. The service writes nothing to the shop.

When the shop cannot be read, or has not handed over its integration user's key yet, the service answers 503 and the till
applies the subscription's down answer (``allow_and_flag`` in this manifest: the sale goes on and is flagged). When the
shop refuses the key (401 or 403: a key withdrawn, a user disabled, a right not given), a sale it would have to read for
is refused in words that say so: a duty-free sale is never made unchecked because of a refused key.

ONE SHOP (env or an env file):
    IVN_CHECK_SECRET   the check's secret (handed back at install as pp_dfa:sub:allowance)
    IVN_SHOP_URL       the shop's address, e.g. https://shop.example.com
    IVN_SHOP_KEY       the app's integration user's key, "<api key>:<api secret>"
MANY SHOPS (the app template's handshake, tools/app_template/service/shops.py; guide chapter 14b):
    IVN_LIBRARY_APP    the App library's id (ivendnext_dfa), with IVN_SHOPS_TABLE (CitiXsys hosting) or IVN_SHOPS_FILE.
                       Each shop connects itself after its install and hands over the check's secret and its integration
                       user's key ("user:<email>": "<api key>:<api secret>"); every call names its shop (X-iVendNext-Site).
DFA_PREFIX (default PP DFA; IVENDNEXT DFA for the library's app) · PORT (default 8080)

    python3 service/app.py [service/.env.local]
"""

from __future__ import annotations

import http.client
import json
from concurrent.futures import ThreadPoolExecutor
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
import dutyfree  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402

KEY, ROUTE = "allowance", "/dfa/check"   # the subscription's key in the manifest; its secret is "<app>:sub:<key>"
KEPT_TTL, READ_TIMEOUT = 60, 0.9         # four steps of reads at most (settings and groups; items and earlier sales; every
                                         # earlier sale at once; the rest of the items), each read 0.9 s per wait on its
                                         # connection, inside the check's 5 s; a slower shop gets the down answer
EARLIER_MAX = 20                         # a passenger's earlier sales on one pass read at most
KEY_REFUSED = ("Duty-free allowance cannot read your shop: it refused the app's user. "
               "Ask your administrator to check the app's setup.")


class ShopUnreadable(Exception):
    pass


class KeyRefused(ShopUnreadable):
    """The shop answered 401 or 403 to the app's user key: a key withdrawn, a user disabled or a right not given (the
    app reads Item Group, Item and POS Invoice), not an outage."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


def _like(text: str) -> str:
    """``text`` as the start of a ``like`` filter: its own ``%``, ``_`` and ``\\`` matched as written."""
    return "".join("\\" + c if c in "%_\\" else c for c in text) + "%"


class ShopApi:
    """The reads the service makes, with the shop's own key. Swapped for a stand-in in the tests."""

    def _get(self, url: str, key: str, path: str, query: dict | None = None, missing=False):
        q = f"?{urllib.parse.urlencode(query)}" if query else ""
        req = urllib.request.Request(f"{url.rstrip('/')}{path}{q}",
                                     headers={"Authorization": f"token {key}", "Accept": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=READ_TIMEOUT) as r:
                return json.loads(r.read() or b"{}") or {}
        except urllib.error.HTTPError as e:
            e.close()
            if missing and e.code == 404:
                return None
            raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)(f"the shop answered {e.code}") from None
        except (OSError, http.client.HTTPException, ValueError) as e:   # OSError: URLError, timeouts, TLS, a cut
            raise ShopUnreadable(type(e).__name__) from None             # connection; HTTPException: a cut answer

    @staticmethod
    def _data(out, kind):
        data = out.get("data") if isinstance(out, dict) else None
        if not isinstance(data, kind):
            raise ShopUnreadable("the shop's answer is not records")
        return data

    def settings(self, url: str, key: str, prefix: str):
        """The record ``Default`` of ``<prefix> Settings``, or ``None`` when the shop has not made it."""
        out = self._get(url, key, "/api/resource/" + urllib.parse.quote(f"{prefix} Settings") + "/Default", missing=True)
        return None if out is None else self._data(out, dict)

    def groups(self, url: str, key: str, prefix: str) -> list:
        """Every item group, with its place in the tree and the app's two fields."""
        p = prefix.lower().replace(" ", "_")
        return self._data(self._get(url, key, "/api/resource/Item%20Group", {
            "fields": json.dumps(["name", "lft", "rgt", f"{p}_allowance", f"{p}_unit"]), "limit_page_length": 0}), list)

    def items(self, url: str, key: str, prefix: str, codes: list) -> list:
        """The named items' stock unit and *Counts toward the allowance as*."""
        p = prefix.lower().replace(" ", "_")
        return self._data(self._get(url, key, "/api/resource/Item", {
            "fields": json.dumps(["name", "stock_uom", f"{p}_counts_as"]), "filters": json.dumps([["name", "in", codes]]),
            "limit_page_length": 0}), list)

    def uoms(self, url: str, key: str, code: str) -> list:
        """One item's units and how many stock units each holds."""
        doc = self._data(self._get(url, key, "/api/resource/Item/" + urllib.parse.quote(code, safe="")), dict)
        return doc.get("uoms") or []

    def earlier(self, url: str, key: str, attribute: str, pass_text: str) -> list:
        """The names of the submitted POS Invoices whose boarding pass starts as this one does."""
        child = "POS Invoice Sale Attribute"
        rows = self._data(self._get(url, key, "/api/resource/POS%20Invoice", {
            "fields": json.dumps(["name"]), "limit_page_length": EARLIER_MAX,
            "filters": json.dumps([[child, "sale_attribute", "=", attribute],
                                   [child, "attribute_value", "like", _like(pass_text[:dutyfree.PASS_KEY])],
                                   ["docstatus", "=", 1]])}), list)
        return [r.get("name") for r in rows if isinstance(r, dict) and isinstance(r.get("name"), str)]

    def sale(self, url: str, key: str, name: str) -> list:
        """One submitted sale's lines."""
        doc = self._data(self._get(url, key, "/api/resource/POS%20Invoice/" + urllib.parse.quote(name, safe="")), dict)
        return doc.get("items") or []


def _num(v) -> float:
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0.0


class Service:
    def __init__(self, conf: dict, store=None, api=None, clock=time.monotonic, now=time.time):
        self.prefix = (conf.get("DFA_PREFIX") or "PP DFA").strip()
        self.field = self.prefix.lower().replace(" ", "_") + "_counts_as"
        self.app = (conf.get("IVN_LIBRARY_APP") or "").strip()
        self.api, self.clock, self.now, self.kept, self.lock = api or ShopApi(), clock, now, {}, threading.Lock()
        if self.app:                                    # many shops: each connects itself
            self.store = store or shops.open_store(conf)
        else:                                           # one shop, from the settings
            self.secret = conf["IVN_CHECK_SECRET"]
            self.shop = {"url": conf["IVN_SHOP_URL"].rstrip("/"), "key": conf["IVN_SHOP_KEY"]}

    def caller(self, headers) -> tuple[str, list[str], dict | None]:
        """(the shop's name for the cache, the secrets this call may be signed with, the shop's address and key)."""
        if not self.app:
            return "-", [self.secret], self.shop
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        secrets = [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{KEY}")]
        users = sorted(k for k in (record or {}).get("secrets") or {} if k.startswith("user:"))
        shop = {"url": record["url"], "key": record["secrets"][users[0]]} if record and users else None
        return site or "", secrets, shop

    def shop_rules(self, name: str, shop: dict | None) -> tuple[dict, dict]:
        """(the shop's settings, its item groups), kept KEPT_TTL seconds for that shop and that key."""
        if not shop:
            raise ShopUnreadable("the shop has not handed over its integration user's key")
        now = self.clock()
        with self.lock:
            hit = self.kept.get(name)
        if hit and hit[1] == shop["key"] and now - hit[0] < KEPT_TTL:
            return hit[2]
        with ThreadPoolExecutor(max_workers=2) as pool:
            s = pool.submit(self.api.settings, shop["url"], shop["key"], self.prefix)
            g = pool.submit(self.api.groups, shop["url"], shop["key"], self.prefix)
            kept = (dutyfree.settings_of(s.result()), dutyfree.groups_of(g.result(), self.prefix))
        with self.lock:
            self.kept[name] = (now, shop["key"], kept)
        return kept

    def amounts(self, shop: dict, ctx: dict, settings: dict, groups: dict, pass_text: str) -> tuple[list, set]:
        """(``(item_group, amount)`` rows for this sale's lines and the passenger's earlier sales, the limited groups this
        sale's own lines fall under). Amounts are in each allowance's measure: stock units times *Counts toward*."""
        url, key = shop["url"], shop["key"]
        mine = [x for x in ctx["lines"] if dutyfree.limited_groups(x["item_group"], groups)]
        touched = {g for x in mine if x["qty_milli"] > 0 for g in dutyfree.limited_groups(x["item_group"], groups)}
        if not touched:
            return [], touched
        codes = sorted({x["item_code"] for x in mine})
        with ThreadPoolExecutor(max_workers=EARLIER_MAX + 2) as pool:   # every earlier sale in one step
            items_f = pool.submit(self.api.items, url, key, self.prefix, codes)
            names_f = pool.submit(self.api.earlier, url, key, f"{self.prefix} {dutyfree.PASS}", pass_text) \
                if settings["earlier"] else None
            items = {r.get("name"): r for r in items_f.result() if isinstance(r, dict)}
            if set(codes) - set(items):
                raise ShopUnreadable("an item on the sale could not be read")
            names = names_f.result() if names_f else []
            earlier = [row for lines in pool.map(lambda n: self.api.sale(url, key, n), names)
                       for row in lines if isinstance(row, dict) and isinstance(row.get("item_group"), str)
                       and dutyfree.limited_groups(row["item_group"], groups)]
            more = sorted({r.get("item_code") for r in earlier if isinstance(r.get("item_code"), str)} - set(items))
            other_units = sorted({x["item_code"] for x in mine if x["uom"] != items[x["item_code"]].get("stock_uom")})
            more_f = pool.submit(self.api.items, url, key, self.prefix, more) if more else None
            units = dict(zip(other_units, pool.map(lambda c: self.api.uoms(url, key, c), other_units)))
            if more_f:
                items.update({r.get("name"): r for r in more_f.result() if isinstance(r, dict)})

        def per_unit(code):
            return _num((items.get(code) or {}).get(self.field)) or 1.0       # blank or 0: each unit counts 1

        rows = []
        for x in mine:
            factor = 1.0
            if x["item_code"] in units:
                factor = next((_num(u.get("conversion_factor")) for u in units[x["item_code"]]
                               if isinstance(u, dict) and u.get("uom") == x["uom"]), 0.0)
                if not factor:
                    raise ShopUnreadable("a line's unit is not one of its item's")
            rows.append((x["item_group"], x["qty_milli"] / 1000 * factor * per_unit(x["item_code"])))
        rows += [(r["item_group"], _num(r.get("stock_qty")) * per_unit(r.get("item_code"))) for r in earlier]
        return rows, touched

    def judge(self, name: str, shop: dict | None, ctx: dict) -> dict:
        pass_text = dutyfree.pass_of(ctx, self.prefix)
        if not pass_text:
            return {"verdict": "refuse", "reason": dutyfree.NO_PASS}
        settings, groups = self.shop_rules(name, shop)
        problem = dutyfree.pass_problem(pass_text, settings, dutyfree.today_at(settings["hours"], self.now()))
        if problem:
            return {"verdict": "refuse", "reason": problem}
        rows, touched = self.amounts(shop, ctx, settings, groups, pass_text)
        reason = dutyfree.over_allowance(rows, groups, touched)
        return {"verdict": "refuse", "reason": reason} if reason else {"verdict": "allow"}

    def answer(self, path: str, headers, raw: bytes) -> tuple[int, dict]:
        if path != ROUTE:
            return 404, {"error": "not found"}
        try:
            name, secrets, shop = self.caller(headers)
        except Exception:               # noqa: BLE001 — the shops store did not answer: nothing was checked
            return 503, {"error": "unavailable"}
        ts, sig = headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature")
        if not secrets or all(dutyfree.verify(ts, sig, raw, s) for s in secrets):
            return 401, {"error": "the signature does not match"}   # the same words for a site the app does not know
        try:
            ctx = dutyfree.check_context(json.loads(raw))
        except ValueError as e:         # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if not dutyfree.sells(ctx):
            return 200, {"verdict": "allow"}            # a refund: nothing leaves the shop, nothing to read
        try:
            return 200, self.judge(name, shop, ctx)
        except KeyRefused:
            return 200, {"verdict": "refuse", "reason": KEY_REFUSED}
        except (ShopUnreadable, ValueError) as e:       # the shop did not answer, or not with records: nothing was judged
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "the shop cannot be read"}

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"status": "ok"}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > dutyfree.BODY_MAX:
            return 413, {"error": "too large"}
        if self.app and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw)
        return self.answer(path, headers, raw)


def _log(log, rid: str, path: str, code: int, t0: float):
    """One line per call: never the body, the context, a secret or a signature."""
    log.write(json.dumps({"request": rid, "route": path[:40], "status": code, "ms": int((time.monotonic() - t0) * 1000)}) + "\n")
    log.flush()


def make_server(svc: Service, port: int, log=sys.stdout):
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
                code, out = svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= dutyfree.BODY_MAX else None)
                return self._send(code, out)
            finally:
                _log(log, rid, self.path, code, t0)

        def do_GET(self):
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):     # the framework's own access line carries the path; keep it off
            pass

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    _log(sys.stdout, (headers.get("X-iVendNext-Request-Id") or "-")[:40], path, code, t0)
    return code, out


# As a function on CitiXsys hosting (app.json "runs": "function"; guide chapter 14b): settings from the environment.
lambda_handler = function.entry(lambda: Service(dict(os.environ)), handle)


def env_file(path: str) -> dict:
    out = {}
    for line in open(path):
        if "=" in line and not line.startswith("#"):
            k, v = line.rstrip("\n").split("=", 1)
            out[k] = v
    return out


def main():
    conf = dict(os.environ, **(env_file(sys.argv[1]) if len(sys.argv) > 1 else {}))
    if not (conf.get("IVN_LIBRARY_APP") or all(conf.get(k) for k in ("IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"))):
        raise SystemExit("set IVN_CHECK_SECRET, IVN_SHOP_URL and IVN_SHOP_KEY (one shop), "
                         "or IVN_LIBRARY_APP with a store (many shops): the app does not start without a way to check a call")
    srv = make_server(Service(conf), int(conf.get("PORT") or 8080))
    signal.signal(signal.SIGTERM, lambda *_: threading.Thread(target=srv.shutdown, daemon=True).start())
    print(json.dumps({"listening": srv.server_address[1]}), flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
