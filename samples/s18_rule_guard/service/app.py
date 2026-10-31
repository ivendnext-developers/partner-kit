"""S18 — *Members-only rule guard*: the partner's service behind the shop's check before payment (standard library only).

    POST /rgd/check            the shop's signed check (``check/1``)  →  200 {"verdict": "allow" | "refuse" | "ask", ...}
    GET  /health               200 {"ok": 1}
    POST /ivendnext/connect    many shops: a shop's site hands over its library key and secrets (the app template's
    POST /ivendnext/disconnect handshake, tools/app_template/service/shops.py; guide chapter 14b)

The till sends the priced basket; the service answers by the shop's OWN rule (``rule.decide``): the shop's ``<prefix> Rule``
records (``rule.rules_of``), read back with the shop's integration user's key once the call's signature holds, and kept
one minute (``RULES_TTL``), so a changed rule applies within a minute. It writes nothing. A bad signature is a 401, a body
it cannot read a 400, and a shop it cannot read a 503: the shop then applies the down answer the subscription declares
(this manifest declares ``refuse``, so an outage never sells a members-only item). A shop that has not handed over its
user's key yet, or that refuses it, is answered *refuse*, in words that say so. A return is judged only for the items it
sells (an exchange); one that sells nothing reads nothing.

It runs in one of two ways:
  ONE SHOP — you hold its secret:   python3 service/app.py service/.env.local
    PP_POINT_SECRET (handed back at install as pp_rgd:sub:guard), PP_PORT (8141), and the shop to read the rule from:
    IVN_SHOP_URL and IVN_SHOP_KEY (the integration user's "<api key>:<api secret>").
  MANY SHOPS — each connects itself after it installs the app from the App library:
    IVN_LIBRARY_APP (the app's id in the library, e.g. ivendnext_rgd; a call is checked with that shop's secret
    "<IVN_LIBRARY_APP>:sub:guard", and the rule read with the key of the app's own user that shop's site handed over,
    "user:<email>"), and IVN_SHOPS_TABLE (on CitiXsys hosting) or IVN_SHOPS_FILE (elsewhere).
    On CitiXsys hosting it runs as a FUNCTION, paid per call (app.json "runs": "function"; ``lambda_handler`` below).
  Either way: RGD_PREFIX (PP RGD; IVENDNEXT RGD for the library's app), the prefix of the shop's Rule record type.
  A laptop run with no shop to read: PP_MEMBERS_ONLY_ITEMS, PP_MEMBERS_ONLY_GROUPS, PP_MEMBER_GROUPS (comma lists),
  PP_ASK_ABOVE (whole units, blank = off) instead.
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

SAMPLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KIT = os.path.dirname(os.path.dirname(SAMPLE))
sys.path.insert(0, SAMPLE)
sys.path.append(os.path.join(KIT, "tools", "app_template", "service"))   # the template's handshake, never a copy
import function  # noqa: E402
import rule  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

KEY, ROUTE = "guard", "/rgd/check"     # the subscription's key in the manifest; its secret is "<app>:sub:<key>"
RULES_TTL, READ_TIMEOUT = 60, 2.0      # a shop's rule is kept a minute; one read must leave time inside the check's 3 s
NOT_SET_UP = "Member rule guard is not set up yet: its key has not arrived. Ask your administrator to press Connect again."
KEY_REFUSED = "Member rule guard cannot read your rules: your shop refused its key. Ask your administrator to press Connect again."


class ShopUnreadable(Exception):
    pass


class KeyRefused(ShopUnreadable):
    """The shop answered 401 or 403 to the app's user key: a key withdrawn or a user disabled, not an outage."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):        # a key never travels to another host
        return None


class ShopApi:
    """The one read the service makes, with the shop's own key. Swapped for a stand-in in the tests."""

    def rules(self, url: str, key: str, prefix: str) -> list:
        """The shop's switched-on Rule records (every one: ``limit_page_length`` 0). Any refusal is unreadable."""
        q = urllib.parse.urlencode({"fields": json.dumps(list(rule.RULE_FIELDS)),
                                    "filters": json.dumps([["enabled", "=", 1]]), "limit_page_length": 0})
        req = urllib.request.Request(f"{url.rstrip('/')}/api/resource/{urllib.parse.quote(prefix + ' Rule')}?{q}",
                                     headers={"Authorization": f"token {key}", "Accept": "application/json"})
        try:
            with urllib.request.build_opener(_NoRedirect).open(req, timeout=READ_TIMEOUT) as r:
                return (json.loads(r.read() or b"{}") or {}).get("data")
        except urllib.error.HTTPError as e:
            e.close()
            raise (KeyRefused if e.code in (401, 403) else ShopUnreadable)(f"the shop answered {e.code}") from None
        except (OSError, http.client.HTTPException, ValueError, AttributeError) as e:   # OSError: URLError, timeouts,
            raise ShopUnreadable(type(e).__name__) from None                            # TLS, a cut connection


class Service:
    def __init__(self, conf: dict, api=None, clock=time.monotonic):
        self.rules = rule.rules_from(conf)          # a laptop run with no shop to read only
        self.prefix = (conf.get("RGD_PREFIX") or "PP RGD").strip()
        self.app = oneshop.value(conf, oneshop.MANY)
        self.store = shops.open_store(conf) if self.app else None
        one = {} if self.app else oneshop.settings(conf, ["PP_POINT_SECRET"], ["IVN_SHOP_URL", "IVN_SHOP_KEY"])
        self.secret = None if self.app else one["PP_POINT_SECRET"]
        if not self.app and bool(one["IVN_SHOP_URL"]) != bool(one["IVN_SHOP_KEY"]):
            raise SystemExit("set both IVN_SHOP_URL and IVN_SHOP_KEY, or neither")   # never fall back to the settings rule
        self.one = ({"url": one["IVN_SHOP_URL"].rstrip("/"), "key": one["IVN_SHOP_KEY"]}
                    if not self.app and one["IVN_SHOP_URL"] else None)
        self.api, self.clock = api or ShopApi(), clock
        self.kept, self.lock = {}, threading.Lock()
        self.keys = None           # the library's public keys: the pinned ones unless a test gives its own

    def secrets(self, headers) -> tuple[str, dict | None, list[str]]:
        """(the site the call names, its shop record, what this call may be signed with): the one shop's secret, or
        that of the shop the call names."""
        if self.store is None:
            return "-", None, [self.secret]
        site = shops.site_of(headers.get(shops.SITE_HEADER))
        record = self.store.get(site) if site else None
        return site or "", record, [s.decode() for s in shops.secrets_for(record, f"{self.app}:sub:{KEY}")]

    def rules_for(self, site: str, record: dict | None) -> dict | None:
        """The rule the shop keeps in its own Rule records, kept RULES_TTL seconds; None when the shop has not handed over
        its integration user's key yet. Called only after the call's signature holds, so only a shop makes us read it."""
        if self.store is None and self.one is None:
            return self.rules
        users = sorted(k for k in ((record or {}).get("secrets") or {}) if k.startswith("user:"))
        shop = self.one or ({"url": record["url"], "key": record["secrets"][users[0]]} if users else None)
        if shop is None:
            return None
        now = self.clock()
        with self.lock:
            hit = self.kept.get(site)
        if hit and hit[1] == shop["key"] and now - hit[0] < RULES_TTL:
            return hit[2]
        rules = rule.rules_of(self.api.rules(shop["url"], shop["key"], self.prefix))
        with self.lock:
            self.kept[site] = (now, shop["key"], rules)
        return rules

    def check(self, headers, raw: bytes) -> tuple[int, dict]:
        try:
            site, record, secrets = self.secrets(headers)
        except Exception as e:     # noqa: BLE001 — the store did not answer: nothing was checked
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)   # the class only: no shop data
            return 503, {"error": "unavailable"}
        whys = [rule.verify(headers.get("X-iVendNext-Timestamp"), headers.get("X-iVendNext-Signature"), raw, s)
                for s in secrets] or ["the signature does not match"]
        if "" not in whys:
            return 401, {"error": whys[0]}
        if testcall.is_test(headers):               # checked as a real call; the point itself does not run
            return testcall.answer(KEY)
        try:
            ctx = rule.context_of(json.loads(raw))
        except ValueError as e:      # json's own errors are ValueErrors too
            return 400, {"error": str(e)}
        if not rule.sold_lines(ctx):   # a return that sells nothing: nothing to judge, nothing to read
            return 200, {"verdict": "allow"}
        try:
            rules = self.rules_for(site, record)
        except KeyRefused:
            return 200, {"verdict": "refuse", "reason": KEY_REFUSED}
        except (ShopUnreadable, ValueError) as e:     # the shop did not answer, or not with records: nothing was judged
            print(json.dumps({"error": type(e).__name__}), file=sys.stderr, flush=True)
            return 503, {"error": "unavailable"}
        if rules is None:
            return 200, {"verdict": "refuse", "reason": NOT_SET_UP}
        return 200, rule.decide(ctx, rules)

    def handle(self, method: str, path: str, headers, raw: bytes | None) -> tuple[int, dict]:
        """One call: (status, answer). The web server below and the function entry both call this."""
        if method == "GET":
            return (200, {"ok": 1}) if path == "/health" else (404, {"error": "not found"})
        if raw is None or len(raw) > rule.BODY_MAX:
            return 413, {"error": "too large"}
        if self.store is not None and path in (shops.CONNECT, shops.DISCONNECT):
            return shops.handle(self.store, self.app, path, headers, raw, self.keys)
        if path == ROUTE:
            return self.check(headers, raw)
        return 404, {"error": "not found"}


def make_handler(svc: Service):
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
            n = int(self.headers.get("Content-Length") or 0)
            self._send(*svc.handle("POST", self.path, self.headers, self.rfile.read(n) if 0 <= n <= rule.BODY_MAX else None))

        def do_GET(self):
            self._send(*svc.handle("GET", self.path, self.headers, b""))

        def log_message(self, fmt, *args):
            sys.stderr.write("s18 %s\n" % (fmt % args))   # the request line only: no header, no body, no secret

    return Handler


def handle(svc: Service, method: str, path: str, headers, raw: bytes) -> tuple[int, dict]:
    """The function's call: the answer, and one log line (the status and the time; never the body or a secret)."""
    t0 = time.monotonic()
    code, out = svc.handle(method, path, headers, raw)
    print(json.dumps({"status": code, "path": path[:40], "ms": int((time.monotonic() - t0) * 1000)}), flush=True)
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


if __name__ == "__main__":
    conf = env(sys.argv[1])
    srv = ThreadingHTTPServer(("0.0.0.0", int(conf.get("PP_PORT") or 8141)), make_handler(Service(conf)))
    print(f"s18 rule guard on :{srv.server_port}", flush=True)
    srv.serve_forever()
