"""S37's service over the wire: each route checked with its own secret, the shop's settings, item groups and items' ages
read with the app's key and kept a minute, a sale's asks remembered, one shop or many (the app template's handshake), and
the down cases the till turns into its down answer.

    python3 -m unittest discover -s samples/s37_age_check/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import io
import json
import os
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service"), str(HERE)]
import app  # noqa: E402
import shops  # noqa: E402
from test_rules import GROUPS, ITEMS, NOW, SETTINGS, context, line, scan  # noqa: E402

SCAN, CHECK = "scan-secret-1", "check-secret-1"
URL = "https://shop.example"
ONE = {"IVN_SCAN_SECRET": SCAN, "IVN_CHECK_SECRET": CHECK, "IVN_SHOP_URL": URL, "IVN_SHOP_KEY": "k:s"}


def raw_of(ctx, point="check/1"):
    return json.dumps({"point": point, "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}
    if site:
        h[shops.SITE_HEADER] = site
    return h


class Api:
    """A stand-in for the shop's reads, keyed by the shop's address; records every call."""

    def __init__(self):
        self.settings_by, self.groups_by, self.items_by = {URL: SETTINGS}, {URL: GROUPS}, {URL: ITEMS}
        self.calls, self.down = [], False

    def _gate(self):
        if self.down:
            raise app.ShopUnreadable("down")

    def settings(self, url, key, prefix):
        self.calls.append(("settings", url, key, prefix))
        self._gate()
        return self.settings_by.get(url)

    def groups(self, url, key, prefix):
        self.calls.append(("groups", url, key, prefix))
        self._gate()
        return self.groups_by.get(url)

    def items(self, url, key, prefix, codes):
        self.calls.append(("items", url, key, tuple(codes)))
        self._gate()
        return [i for i in self.items_by.get(url, []) if i["name"] in codes]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class OneShop(unittest.TestCase):
    def setUp(self):
        self.api, self.clock = Api(), Clock()
        self.svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: NOW)

    def check(self, ctx, secret=CHECK, ts=None):
        raw = raw_of(ctx)
        return self.svc.answer("/age/check", signed(raw, secret, ts), raw)

    def scan(self, ctx, secret=SCAN):
        raw = raw_of(ctx, "capture/1")
        return self.svc.answer("/age/scan", signed(raw, secret), raw)

    def test_a_restricted_scan_shows_the_shops_day_and_records_the_check(self):
        code, out = self.scan(scan())
        self.assertEqual((code, out["verdict"]), (200, "notice"))
        self.assertEqual(out["message"], "WHISKY: customers 18 or over. Born on or before 22 Oct 2008. Ask for ID if they look under 25.")
        self.assertEqual(out["sale_attributes"], [{"sale_attribute": "PP AGE ID Checked", "attribute_value": "18 or over"}])

    def test_the_shops_hours_decide_the_date_shown(self):
        svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: NOW + 9.5 * 3600)   # the 23rd in Dubai
        raw = raw_of(scan(), "capture/1")
        self.assertIn("Born on or before 23 Oct 2008", svc.answer("/age/scan", signed(raw, SCAN), raw)[1]["message"])

    def test_a_sale_asked_about_is_not_asked_again_for_that_age_or_below(self):
        self.assertEqual(self.scan(scan("VAPE", "Vapes"))[1]["verdict"], "notice")
        self.assertEqual(self.scan(scan("WHISKY", "Spirits"))[1], {"verdict": "allow"})
        self.assertEqual(self.scan(scan("WHISKY", "Spirits", sale_ref="sale-2"))[1]["verdict"], "notice")

    def test_a_sales_first_scan_has_no_reference_and_is_asked_again(self):
        self.assertEqual(self.scan(scan(sale_ref=""))[1]["verdict"], "notice")
        self.assertEqual(self.scan(scan(sale_ref="sale-9"))[1]["verdict"], "notice")
        self.assertEqual(self.scan(scan(sale_ref="sale-9"))[1], {"verdict": "allow"})

    def test_a_variant_is_judged_by_its_templates_age_read_in_a_second_step(self):
        out = self.check(context([line("POD-MINT", "Food", n=1)]))[1]
        self.assertTrue(out["reason"].startswith("Line 1: POD-MINT is for customers 21 or over."), out)
        self.assertEqual([c[3] for c in self.api.calls if c[0] == "items"], [("POD-MINT",), ("POD",)])
        self.assertEqual(self.check(context([line("POD-MINT", "Food")], checked="21"))[1], {"verdict": "allow"})
        self.assertEqual(len([c for c in self.api.calls if c[0] == "items"]), 2)          # both kept a minute

    def test_an_item_with_no_age_is_allowed_with_nothing_shown(self):
        self.assertEqual(self.scan(scan("BREAD", "Food"))[1], {"verdict": "allow"})

    def test_the_check_refuses_a_restricted_line_the_sale_has_no_check_for(self):
        out = self.check(context([line("WHISKY", "Spirits", n=1)]))[1]
        self.assertEqual(out["verdict"], "refuse")
        self.assertTrue(out["reason"].startswith("Line 1: WHISKY is for customers 18 or over."))

    def test_the_check_allows_a_recorded_check_that_covers_every_line(self):
        ctx = context([line("WHISKY", "Spirits", n=1), line("VAPE", "Vapes", n=2)], checked="21 or over")
        self.assertEqual(self.check(ctx), (200, {"verdict": "allow"}))

    def test_a_refund_is_allowed_without_reading_anything(self):
        self.assertEqual(self.check(context([line("WHISKY", "Spirits", -2)], stage="return")), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_each_route_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(), secret=SCAN)[0], 401)
        self.assertEqual(self.scan(scan(), secret=CHECK)[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/age/check", signed(raw, CHECK), raw.replace(b"WHISKY", b"WHISKE"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(self.svc.answer("/age/check", signed(raw, CHECK), raw)[0], 400)
        raw = raw_of(scan(), "check/1")
        self.assertEqual(self.svc.answer("/age/scan", signed(raw, SCAN), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/dfa/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_settings_groups_and_items_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.clock.t += 59
        self.check(context())
        self.assertEqual(self.api.calls, [("settings", URL, "k:s", "PP AGE"), ("groups", URL, "k:s", "PP AGE"),
                                          ("items", URL, "k:s", ("WHISKY",))])
        self.check(context([line("WHISKY", "Spirits"), line("KNIFE", "Food")]))
        self.assertEqual(self.api.calls[-1], ("items", URL, "k:s", ("KNIFE",)))           # only the item not kept
        self.clock.t += 2
        self.check(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)
        self.assertEqual(self.api.calls[-1], ("items", URL, "k:s", ("WHISKY",)))

    def test_no_settings_record_is_utc_and_see_their_id(self):
        self.api.settings_by[URL] = None
        self.assertTrue(self.scan(scan())[1]["message"].endswith("Born on or before 22 Oct 2008. See their ID."))

    def test_the_shop_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context())[0], 503)
        self.assertEqual(self.scan(scan())[0], 503)

    def test_an_item_the_shop_does_not_return_is_a_503(self):
        self.assertEqual(self.check(context([line("NEW-RUM", "Spirits")]))[0], 503)
        self.assertEqual(self.scan(scan("NEW-RUM", "Spirits"))[0], 503)

    def test_groups_that_are_not_records_are_a_503(self):
        self.api.groups_by[URL] = None
        self.assertEqual(self.check(context())[0], 503)

    def test_the_prefix_names_the_sale_detail_and_the_fields(self):
        self.api.groups_by[URL] = [{k.replace("pp_age_", "ivendnext_age_"): v for k, v in g.items()} for g in GROUPS]
        self.api.items_by[URL] = [{k.replace("pp_age_", "ivendnext_age_"): v for k, v in i.items()} for i in ITEMS]
        svc = app.Service(dict(ONE, AGE_PREFIX="IVENDNEXT AGE"), api=self.api, clock=self.clock, now=lambda: NOW)
        raw = raw_of(scan(), "capture/1")
        out = svc.answer("/age/scan", signed(raw, SCAN), raw)[1]
        self.assertEqual(out["sale_attributes"][0]["sale_attribute"], "IVENDNEXT AGE ID Checked")
        self.assertEqual(self.api.calls[0][3], "IVENDNEXT AGE")
        raw = raw_of(context(checked="18", prefix="PP AGE"))      # another app's sale detail is not this app's check
        self.assertEqual(svc.answer("/age/check", signed(raw, CHECK), raw)[1]["verdict"], "refuse")
        raw = raw_of(context(checked="18", prefix="IVENDNEXT AGE"))
        self.assertEqual(svc.answer("/age/check", signed(raw, CHECK), raw)[1], {"verdict": "allow"})


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_age:sub:scan": f"scan-{n}", "ivendnext_age:sub:check": f"check-{n}", "user:age@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_age:sub:check": "check-c"}})     # no user key
        self.api = Api()
        for site, alcohol in ((self.A, 18), (self.B, 21)):
            u = f"https://{site}"
            groups = [dict(g, pp_age_min_age=alcohol) if g["name"] == "Alcohol" else g for g in GROUPS]
            self.api.settings_by[u], self.api.groups_by[u], self.api.items_by[u] = SETTINGS, groups, ITEMS
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_age", "AGE_PREFIX": "PP AGE"}, store=self.store, api=self.api,
                               clock=Clock(), now=lambda: NOW)

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context(checked="18"))
        return self.svc.answer("/age/check", signed(raw, secret, site=site), raw)

    def scan(self, secret, site, sale_ref="sale-1"):
        raw = raw_of(scan(sale_ref=sale_ref), "capture/1")
        return self.svc.answer("/age/scan", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_ages_with_its_own_key(self):
        self.assertEqual(self.check("check-a", self.A)[1]["verdict"], "allow")         # A: alcohol at 18
        self.assertEqual(self.check("check-b", self.B)[1]["verdict"], "refuse")        # B: alcohol at 21
        seen = sorted({c[1:3] for c in self.api.calls})
        self.assertEqual(seen, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_each_route_takes_its_own_secret_and_another_shops_is_refused(self):
        self.assertEqual(self.scan("scan-a", self.A)[0], 200)
        self.assertEqual(self.scan("check-a", self.A)[0], 401)
        self.assertEqual(self.check("check-b", self.A)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.check("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.check("check-a", None)[0], 401)

    def test_a_shop_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.check("check-c", "shop-c.ivendnext.com")[0], 503)

    def test_the_ages_and_the_asks_are_kept_per_shop(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)
        self.assertEqual(self.scan("scan-a", self.A)[1]["verdict"], "notice")
        self.assertEqual(self.scan("scan-b", self.B)[1]["verdict"], "notice")      # the same sale reference, another shop

    def test_a_new_key_reads_the_shop_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_age:sub:check": "check-a", "user:age@x": "key-a2:sec-a2"}})
        self.check("check-a", self.A)
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "settings"], ["key-a:sec-a", "key-a2:sec-a2"])
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "items"], ["key-a:sec-a", "key-a2:sec-a2"])


class ShopApi(unittest.TestCase):
    """``ShopApi`` against a stand-in shop on a local port: the key, the paths and filters, a missing settings record, an
    error, a cut answer, no redirect."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []

        class Shop(BaseHTTPRequestHandler):
            def do_GET(h):
                cls.seen.append((h.path, h.headers.get("Authorization")))
                path, _, q = h.path.partition("?")
                if "Redirect" in path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/Item%20Group?{q}")
                    h.end_headers()
                    return
                code, body = {
                    "/api/resource/PP%20AGE%20Settings/Default": (200, {"data": SETTINGS}),
                    "/api/resource/NONE%20Settings/Default": (404, {"exc_type": "DoesNotExistError"}),
                    "/api/resource/LOCKED%20Settings/Default": (403, {"exc_type": "PermissionError"}),
                    "/api/resource/CUT%20Settings/Default": (200, None),
                    "/api/resource/LIST%20Settings/Default": (200, {"data": []}),
                    "/api/resource/Item%20Group": (200, {"data": GROUPS}),
                    "/api/resource/Item": (200, {"data": ITEMS[:1]}),
                }[path]
                if body is None:                 # an answer cut short: more promised than sent
                    h.send_response(code)
                    h.send_header("Content-Length", "100")
                    h.end_headers()
                    h.wfile.write(b'{"da')
                    h.wfile.flush()
                    h.connection.shutdown(socket.SHUT_RDWR)
                    return
                data = json.dumps(body).encode()
                h.send_response(code)
                h.send_header("Content-Length", str(len(data)))
                h.end_headers()
                h.wfile.write(data)

            def log_message(h, *a):
                pass

        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.api = app.ShopApi()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def args(self):
        return dict(urllib.parse.parse_qsl(self.seen[-1][0].split("?", 1)[1]))

    def test_reads_the_settings_record_with_the_token_and_none_when_missing(self):
        self.assertEqual(self.api.settings(self.url, "k:s", "PP AGE"), SETTINGS)
        self.assertEqual(self.seen[-1][1], "token k:s")
        self.assertIsNone(self.api.settings(self.url, "k:s", "NONE"))

    def test_reads_every_item_group_with_the_apps_age(self):
        self.assertEqual(self.api.groups(self.url, "k:s", "PP AGE"), GROUPS)
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), a["limit_page_length"]), (["name", "lft", "rgt", "pp_age_min_age"], "0"))

    def test_reads_the_named_items_age(self):
        self.api.items(self.url, "k:s", "PP AGE", ["WHISKY"])
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), json.loads(a["filters"]), a["limit_page_length"]),
                         (["name", "pp_age_min_age", "variant_of"], [["name", "in", ["WHISKY"]]], "0"))

    def test_a_refusal_or_an_answer_that_is_not_records_is_unreadable(self):
        for prefix in ("LOCKED", "LIST"):
            with self.assertRaises(app.ShopUnreadable):
                self.api.settings(self.url, "k:s", prefix)

    def test_a_cut_answer_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.settings(self.url, "k:s", "CUT")

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api._get(self.url, "k:s", "/api/resource/Redirect")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.groups("http://127.0.0.1:9", "k:s", "PP AGE")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": URL, "secrets": {
            "ivendnext_age:sub:scan": "scan-a", "ivendnext_age:sub:check": "check-a", "user:age@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_age", "AGE_PREFIX": "PP AGE"}, store=self.store, api=Api(),
                          now=lambda: NOW)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_scan_and_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context())
        for b64 in (False, True):
            out = self.entry(self.event("/age/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual((out["statusCode"], json.loads(out["body"])["verdict"]), (200, "refuse"))
        raw = raw_of(scan(), "capture/1")
        out = self.entry(self.event("/age/scan", raw, signed(raw, "scan-a", site="shop-a.ivendnext.com")))
        self.assertEqual((out["statusCode"], json.loads(out["body"])["verdict"]), (200, "notice"))
        out = self.entry(self.event("/age/scan", raw, signed(raw, "check-a", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed check, and one log line that carries no shop data."""

    def test_health_a_signed_check_and_a_clean_log(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE, api=Api(), now=lambda: NOW), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            ctx = dict(context(), customer="SECRET CUSTOMER")
            raw = raw_of(ctx)
            req = urllib.request.Request(base + "/age/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            bad = urllib.request.Request(base + "/age/check", data=raw, headers=signed(raw, "x"), method="POST")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(e.exception.code, 401)
            e.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()
        text = log.getvalue()
        self.assertIn('"status": 200', text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn(CHECK, text)


if __name__ == "__main__":
    unittest.main()
