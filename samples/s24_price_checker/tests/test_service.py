"""S24's service: the kiosk's call answered only for a known shop and a switched-on kiosk, the shop read with the app's key
(the Kiosk record kept a minute), the shop's refusals turned into the kiosk's words, the page served with a strict
content policy, one shop or many (the app template's handshake), the function entry, and the three shop reads against a
stand-in shop over HTTP.

    python3 -m unittest discover -s samples/s24_price_checker/tests -p 'test_*.py'
"""

import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service"), str(HERE)]
import app  # noqa: E402
import shops  # noqa: E402
from test_price import KIOSK, TODAY, details  # noqa: E402

CODE = "k3v9q0abcd"
ONE = {"IVN_SHOP_URL": "https://shop.example", "IVN_SHOP_KEY": "k:s"}


class Api:
    """A stand-in for the shop: kiosks by (url, code), items by scan text, prices by item; counts every read."""

    def __init__(self):
        self.kiosks = {("https://shop.example", CODE): dict(KIOSK)}
        self.items = {"4006381333931": {"barcode": "4006381333931", "item_code": "PEN-01", "uom": "Nos"}}
        self.prices = {"PEN-01": details(image="/files/pen.jpg")}
        self.calls, self.down, self.refuse = [], False, set()

    def kiosk(self, url, key, prefix, code):
        self.calls.append(("kiosk", url, key, prefix, code))
        if self.down:
            raise app.ShopUnreadable("down")
        return self.kiosks.get((url, code))

    def scan(self, url, key, text):
        self.calls.append(("scan", url, key, text))
        if self.down:
            raise app.ShopUnreadable("down")
        return dict(self.items.get(text) or {})

    def price(self, url, key, args):
        self.calls.append(("price", url, key, args))
        if args["item_code"] in self.refuse:
            raise app.NotPriced("417")
        return dict(self.prices[args["item_code"]])


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def body(kiosk=CODE, scan="4006381333931", shop=None, date="2026-10-15"):
    return json.dumps({"kiosk": kiosk, "scan": scan, "shop": shop, "date": date}).encode()


def one(api=None, clock=None, **conf):
    return app.Service(dict(ONE, **conf), api=api or Api(), clock=clock or Clock(), today=lambda: TODAY)


class OneShop(unittest.TestCase):
    def test_a_scan_is_priced_by_the_shop_with_the_apps_key(self):
        api = Api()
        code, out = one(api).price(body())
        self.assertEqual((code, out["status"], out["item"], out["price"], out["currency"]), (200, "found", "Blue pen", 10.0, "USD"))
        self.assertEqual(out["image"], "https://shop.example/files/pen.jpg")
        self.assertEqual([c[:3] for c in api.calls], [("kiosk", "https://shop.example", "k:s"),
                                                      ("scan", "https://shop.example", "k:s"),
                                                      ("price", "https://shop.example", "k:s")])
        self.assertEqual(api.calls[0][3], "PP PRC")
        args = api.calls[2][3]
        self.assertEqual((args["selling_price_list"], args["customer"], args["transaction_date"], args["uom"]),
                         ("Standard Selling", "Walk-in", "2026-10-15", "Nos"))

    def test_the_prefix_names_the_record_type(self):
        api = Api()
        one(api, PRC_PREFIX="IVENDNEXT PRC").price(body())
        self.assertEqual(api.calls[0][3], "IVENDNEXT PRC")

    def test_nothing_found_is_said_in_plain_words(self):
        code, out = one().price(body(scan="NO-SUCH"))
        self.assertEqual((code, out["status"]), (200, "not_found"))

    def test_an_item_the_shop_refuses_to_price_is_not_on_sale(self):
        api = Api()
        api.refuse.add("PEN-01")
        self.assertEqual(one(api).price(body())[1]["status"], "not_on_sale")

    def test_an_unknown_or_switched_off_kiosk_is_not_set_up(self):
        api = Api()
        self.assertEqual(one(api).price(body(kiosk="zzzzzzzzzz")), (403, app.price.refusal("not_set_up")))
        api.kiosks[("https://shop.example", CODE)]["enabled"] = 0
        self.assertEqual(one(api).price(body()), (403, app.price.refusal("not_set_up")))
        self.assertNotIn("scan", [c[0] for c in api.calls])           # the shop's items are never read for it

    def test_a_malformed_code_never_reaches_the_shop(self):
        api = Api()
        for bad in ("../x", "", None, "k3v9q0abc/"):
            self.assertEqual(one(api).price(body(kiosk=bad))[0], 403)
        self.assertEqual(api.calls, [])

    def test_a_bad_scan_or_body_is_refused_without_reading_the_shop(self):
        api = Api()
        svc = one(api)
        self.assertEqual(svc.price(body(scan=""))[0], 400)
        self.assertEqual(svc.price(b"not json")[0], 400)
        self.assertEqual(svc.price(b"[1]")[0], 400)
        self.assertEqual(api.calls, [])

    def test_the_shops_store_down_is_unavailable(self):
        class Down:
            def get(self, site):
                raise RuntimeError("store down")
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_prc"}, store=Down(), api=Api(), clock=Clock(), today=lambda: TODAY)
        self.assertEqual(svc.price(body(shop="shop.example")), (503, app.price.refusal("unavailable")))

    def test_the_shop_down_is_unavailable(self):
        api = Api()
        api.down = True
        self.assertEqual(one(api).price(body()), (503, app.price.refusal("unavailable")))

    def test_the_kiosk_record_is_kept_a_minute_so_switching_off_stops_it_within_a_minute(self):
        api, clock = Api(), Clock()
        svc = one(api, clock)
        self.assertEqual(svc.price(body())[0], 200)
        api.kiosks[("https://shop.example", CODE)]["enabled"] = 0
        clock.t += 59
        self.assertEqual(svc.price(body())[0], 200)
        self.assertEqual([c[0] for c in api.calls].count("kiosk"), 1)
        clock.t += 2
        self.assertEqual(svc.price(body())[0], 403)
        self.assertEqual([c[0] for c in api.calls].count("kiosk"), 2)

    def test_a_guesser_cannot_make_the_service_hammer_the_shop(self):
        api, clock = Api(), Clock()
        svc = one(api, clock)
        self.assertEqual(svc.price(body())[0], 200)                  # the real kiosk, seen once
        for i in range(app.MISSES_PER_MINUTE):
            self.assertEqual(svc.price(body(kiosk=f"zzzzzzzz{i:02d}"))[0], 403)
        reads = len(api.calls)
        self.assertEqual(svc.price(body(kiosk="zzzzzzzzyy")), (429, app.price.refusal("busy")))
        self.assertEqual(len(api.calls), reads)                     # the shop was not read again
        clock.t += 30
        self.assertEqual(svc.price(body())[0], 200)                  # the real kiosk is never locked out (cached)
        clock.t += 31                                                # its minute is over, and so are the old guesses
        for i in range(app.MISSES_PER_MINUTE):                       # a fresh minute of guesses
            self.assertEqual(svc.price(body(kiosk=f"yyyyyyyy{i:02d}"))[0], 403)
        self.assertEqual(svc.price(body())[0], 200)                  # the real kiosk is read again all the same
        self.assertEqual(svc.price(body(kiosk="zzzzzzzzyz"))[0], 429)

    def test_the_kiosks_date_reaches_the_pricer_only_within_a_day(self):
        api = Api()
        one(api).price(body(date="2026-10-16"))
        one(api).price(body(date="2027-01-01"))
        self.assertEqual([c[3]["transaction_date"] for c in api.calls if c[0] == "price"], ["2026-10-16", "2026-10-15"])


class Page(unittest.TestCase):
    def test_the_page_is_served_with_a_strict_content_policy_and_no_inline_script(self):
        code, data, h = one().handle("GET", "/", {}, None)
        self.assertEqual((code, h["Content-Type"].split(";")[0]), (200, "text/html"))
        html = data.decode()
        self.assertIn('<script src="kiosk.js" defer></script>', html)
        self.assertEqual(html.count("<script"), 1)
        self.assertNotIn("onclick", html)
        csp = h["Content-Security-Policy"]
        for part in ("default-src 'none'", "script-src 'self'", "connect-src 'self'", "frame-ancestors 'none'"):
            self.assertIn(part, csp)
        self.assertNotIn("unsafe", csp)
        self.assertEqual(h["Referrer-Policy"], "no-referrer")

    def test_every_price_says_offers_are_worked_out_at_the_till(self):
        html = one().handle("GET", "/", {}, None)[1].decode()
        i = html.index('id="price"')
        self.assertIn("Any offer is worked out at the till.", html[i:html.index("</section>", i)])

    def test_the_script_draws_with_text_only(self):
        js = (HERE.parent / "service" / "kiosk.js").read_text()
        self.assertNotIn("innerHTML", js)
        self.assertNotIn("eval(", js)
        self.assertIn("location.hash", js)                         # the shop and kiosk come from the fragment

    def test_a_shop_on_plain_http_may_show_its_pictures_on_the_bench_only(self):
        csp = one(IVN_SHOP_URL="http://localhost:8110").csp()
        self.assertIn("img-src https: http://localhost:8110;", csp)
        self.assertIn("img-src https:;", one().csp())

    def test_other_paths_and_large_bodies(self):
        svc = one()
        self.assertEqual(svc.handle("GET", "/../app.py", {}, None)[0], 404)
        self.assertEqual(svc.handle("GET", "/health", {}, None)[0], 200)
        self.assertEqual(svc.handle("POST", "/prc/price", {}, b"x" * (app.BODY_MAX + 1))[0], 413)
        self.assertEqual(svc.handle("POST", "/ivendnext/connect", {}, b"{}")[0], 404)   # one shop: no handshake


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = shops.FileStore(os.path.join(self.tmp.name, "shops.json"))
        self.api = Api()
        self.api.kiosks[("https://b.example.com", CODE)] = dict(KIOSK, currency="ZAR")
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_prc", "PRC_PREFIX": "IVENDNEXT PRC"}, store=self.store,
                               api=self.api, clock=Clock(), today=lambda: TODAY)

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self, site, **secrets):
        self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": secrets, "previous": {}})

    def test_a_shop_that_did_not_connect_is_not_set_up_and_is_not_read(self):
        self.assertEqual(self.svc.price(body(shop="a.example.com"))[0], 403)
        self.assertEqual(self.svc.price(body(shop="not a site"))[0], 403)
        self.assertEqual(self.api.calls, [])

    def test_a_shop_that_has_not_handed_over_its_user_key_is_not_set_up(self):
        self.connect("a.example.com", **{"ivendnext_prc:sub:x": "s"})
        self.assertEqual(self.svc.price(body(shop="a.example.com"))[0], 403)
        self.assertEqual(self.api.calls, [])

    def test_each_shop_is_read_at_its_own_address_with_its_own_key(self):
        self.connect("shop.example", **{"user:apps@a": "ka:sa"})
        self.connect("b.example.com", **{"user:apps@b": "kb:sb"})
        a, b = self.svc.price(body(shop="shop.example"))[1], self.svc.price(body(shop="B.Example.com"))[1]
        self.assertEqual((a["currency"], b["currency"]), ("USD", "ZAR"))
        self.assertEqual(b["image"], "https://b.example.com/files/pen.jpg")
        self.assertEqual({(c[1], c[2]) for c in self.api.calls},
                         {("https://shop.example", "ka:sa"), ("https://b.example.com", "kb:sb")})

    def test_the_handshake_routes_are_the_templates(self):
        code, data, _ = self.svc.handle("POST", shops.CONNECT, {}, b"{}")
        self.assertEqual((code, json.loads(data)), (400, {"refused": "bad_request"}))


class Wire(unittest.TestCase):
    def test_the_web_server_and_the_function_answer_alike(self):
        srv = app.make_server(one(), 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/") as r:
                page = (r.status, r.headers["Content-Type"], r.headers["Content-Security-Policy"])
            req = urllib.request.Request(base + "/prc/price", data=body(), headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as r:
                over_wire = json.loads(r.read())
        finally:
            srv.shutdown()
            srv.server_close()
        self.assertEqual(page[:2], (200, "text/html; charset=utf-8"))
        self.assertEqual(over_wire["status"], "found")
        app._KEPT["svc"] = one()
        try:
            got = app.lambda_handler({"httpMethod": "POST", "path": "/prc/price", "headers": {"content-type": "application/json"},
                                      "body": body().decode(), "isBase64Encoded": False})
            pg = app.lambda_handler({"httpMethod": "GET", "path": "/", "headers": {}, "body": ""})
        finally:
            app._KEPT.clear()
        self.assertEqual((got["statusCode"], json.loads(got["body"])), (200, over_wire))
        self.assertEqual((pg["statusCode"], pg["headers"]["Content-Type"], pg["headers"]["Content-Security-Policy"]),
                         (200, page[1], page[2]))


class FakeShop(BaseHTTPRequestHandler):
    """A stand-in for the shop's own API, answering as the shop does (bodies as read on the test bench)."""
    script, seen = {}, []

    def _go(self):
        n = int(self.headers.get("Content-Length") or 0)
        FakeShop.seen.append((self.command, self.path, self.headers.get("Authorization"), self.rfile.read(n) if n else b""))
        code, out = FakeShop.script.get(self.path.split("?")[0], (404, {"exc_type": "DoesNotExistError"}))
        data = json.dumps(out).encode()
        self.send_response(code)
        if code in (301, 302):
            self.send_header("Location", "http://%s:%d/steal" % self.server.server_address)   # the redirect comes back here
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = _go

    def log_message(self, *a):
        pass


class ShopApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeShop)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.srv.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        FakeShop.script, FakeShop.seen = {}, []
        self.api = app.ShopApi()

    K = "/api/resource/PP%20PRC%20Kiosk/" + CODE

    def test_the_kiosk_is_read_with_the_apps_key(self):
        FakeShop.script = {self.K: (200, {"data": KIOSK})}
        self.assertEqual(self.api.kiosk(self.url, "k:s", "PP PRC", CODE), KIOSK)
        self.assertEqual(FakeShop.seen[0][:3], ("GET", self.K, "token k:s"))

    def test_a_404_naming_the_record_is_no_kiosk(self):
        FakeShop.script = {self.K: (404, {"exception": f"frappe.exceptions.DoesNotExistError: PP PRC Kiosk {CODE} not found"})}
        self.assertIsNone(self.api.kiosk(self.url, "k:s", "PP PRC", CODE))

    def test_a_404_that_does_not_name_the_record_is_unreadable_never_no_kiosk(self):
        FakeShop.script = {self.K: (404, {"exception": "DocType PP PRC Kiosk not found"})}
        with self.assertRaises(app.ShopUnreadable):
            self.api.kiosk(self.url, "k:s", "PP PRC", CODE)
        FakeShop.script = {self.K: (403, {"exc_type": "PermissionError"})}
        with self.assertRaises(app.ShopUnreadable):
            self.api.kiosk(self.url, "k:s", "PP PRC", CODE)

    def test_the_lookup_and_the_pricer_are_the_shops_whitelisted_calls(self):
        FakeShop.script = {app.SCAN_BARCODE: (200, {"message": {"item_code": "PEN-01", "uom": "Nos"}}),
                           app.PRICER: (200, {"message": details()})}
        self.assertEqual(self.api.scan(self.url, "k:s", "4006381333931")["item_code"], "PEN-01")
        self.assertEqual(self.api.price(self.url, "k:s", {"item_code": "PEN-01"})["price_list_rate"], 10.0)
        (m1, p1, a1, b1), (m2, p2, a2, b2) = FakeShop.seen
        self.assertEqual((m1, p1, a1, json.loads(b1)), ("POST", app.SCAN_BARCODE, "token k:s", {"search_value": "4006381333931"}))
        self.assertEqual((m2, p2, json.loads(b2)), ("POST", app.PRICER, {"args": {"item_code": "PEN-01"}}))

    def test_the_shops_refusals(self):
        FakeShop.script = {app.SCAN_BARCODE: (417, {"exc_type": "ValidationError"}), app.PRICER: (417, {"exc_type": "ValidationError"})}
        self.assertEqual(self.api.scan(self.url, "k:s", "LOT7"), {})
        with self.assertRaises(app.NotPriced):
            self.api.price(self.url, "k:s", {"item_code": "OLD"})
        FakeShop.script = {app.PRICER: (404, {"exc_type": "DoesNotExistError"})}
        with self.assertRaises(app.ShopUnreadable):                  # a 404 is not "not on sale"
            self.api.price(self.url, "k:s", {"item_code": "PEN-01"})
        FakeShop.script = {app.SCAN_BARCODE: (500, {}), app.PRICER: (500, {})}
        with self.assertRaises(app.ShopUnreadable):
            self.api.scan(self.url, "k:s", "x")
        with self.assertRaises(app.ShopUnreadable):
            self.api.price(self.url, "k:s", {"item_code": "PEN-01"})

    def test_never_a_rate(self):
        with self.assertRaises(ValueError):
            self.api.price(self.url, "k:s", {"item_code": "PEN-01", "rate": 1})
        self.assertEqual(FakeShop.seen, [])

    def test_a_redirect_is_not_followed(self):
        FakeShop.script = {self.K: (302, {})}
        with self.assertRaises(app.ShopUnreadable):
            self.api.kiosk(self.url, "k:s", "PP PRC", CODE)
        self.assertEqual([s[1] for s in FakeShop.seen], [self.K])        # never a second call, with the key, elsewhere

    def test_a_shop_that_does_not_answer_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.scan("http://127.0.0.1:9", "k:s", "x")


if __name__ == "__main__":
    unittest.main()
