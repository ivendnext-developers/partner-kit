"""S56 for many retailers (the app template's handshake): each code checked with its own retailer's secret and answered
with that retailer's own key for the app's user, under the library's prefix; one order per code across every copy of
the function (the shops table's claim); a call before the retailer's key arrives; and the function entry.

    python3 -m unittest discover -s samples/s56_guest_ordering/tests -p 'test_*.py'
"""

import json
import os
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import app  # noqa: E402
import fakeshop as F  # noqa: E402
import gor  # noqa: E402
import shops  # noqa: E402
from test_service import ORDER, Clock, latte  # noqa: E402

APP, A, B = "ivendnext_gor", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "GOR_PREFIX": "IVENDNEXT GOR", "GOR_PAGE_URL": F.PAGE}


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:code": f"cd-{n}", f"{APP}:tillkey": f"tk-{n}", "user:gor@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:code": "cd-c"}})     # no user key yet
        self.doors, self.clock = {}, Clock()
        self.svc = app.Service(LIB, store=self.store, tenants=self.door, now=self.clock)

    def tearDown(self):
        gor.use_prefix("PP GOR")

    def door(self, url, key):
        if url not in self.doors:
            d = F.FakeTenant(codes=[F.code("C1", number=1)])
            d.codes["C1"]["made_for"] = gor.made_for(d.codes["C1"])
            d.key = key
            self.doors[url] = d
        return self.doors[url]

    def token(self, site, secret, record="C1", number=1):
        return f"{record}.{number}.{gor.sign(secret.encode(), site, record, number)}"

    def call(self, path, site, t, svc=None, **extra):
        code, body, _ = (svc or self.svc).handle("POST", path, {}, json.dumps(dict({"s": site, "t": t}, **extra)).encode())
        return code, json.loads(body)

    def test_each_retailer_is_read_with_its_own_key_under_the_librarys_prefix(self):
        for site, n in ((A, "a"), (B, "b")):
            self.assertEqual(self.call("/gor/menu", site, self.token(site, f"cd-{n}"))[1]["state"], "open")
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        for d in self.doors.values():
            self.assertIn("GET IVENDNEXT GOR Code", d.calls)

    def test_another_retailers_code_is_refused(self):
        self.assertEqual(self.call("/gor/menu", A, self.token(A, "cd-b")), (404, {"state": "unknown"}))
        self.assertEqual(self.call("/gor/menu", B, self.token(A, "cd-a")), (404, {"state": "unknown"}))
        self.assertEqual(self.call("/gor/menu", A, self.token(A, "tk-a")), (404, {"state": "unknown"}))   # another secret
        self.assertFalse([d.calls for d in self.doors.values() if d.calls])      # nothing was read

    def test_a_call_before_connect_again_reads_nothing(self):
        code, out = self.call("/gor/menu", "shop-c.ivendnext.com", self.token("shop-c.ivendnext.com", "cd-c"))
        self.assertEqual((code, out), (503, {"state": "unavailable"}))
        self.assertEqual(self.doors, {})

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:code": "cd-a", "user:Administrator": "adm:sec"}))
        self.assertEqual(self.call("/gor/menu", A, self.token(A, "cd-a")), (503, {"state": "unavailable"}))
        self.assertEqual(self.doors, {})

    def test_one_order_a_code_across_every_copy_of_the_function(self):
        other = app.Service(LIB, store=self.store, tenants=self.door, now=self.clock)   # a second copy, the same table
        t = self.token(A, "cd-a")
        self.assertEqual(self.call("/gor/order", A, t, key=ORDER, lines=[latte()])[1]["state"], "sent")
        k2 = "9f1c2b9e-0d4a-4c1e-9a3b-1f2e3d4c5b6a"
        self.assertEqual(self.call("/gor/order", A, t, svc=other, key=k2, lines=[latte()])[1]["state"], "wait")
        self.assertEqual(self.call("/gor/order", B, self.token(B, "cd-b"), svc=other, key=k2, lines=[latte()])[1]["state"],
                         "sent")                                  # another retailer's table is its own
        self.clock.t += gor.SPACING_S + 1
        self.assertEqual(self.call("/gor/order", A, t, svc=other, key=k2, lines=[latte()])[1]["state"], "sent")

    def test_a_shops_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        svc = app.Service(LIB, store=Down())
        self.assertEqual(self.call("/gor/menu", A, self.token(A, "cd-a"), svc=svc), (503, {"state": "unavailable"}))

    def test_the_function_entry_serves_the_page_and_the_calls(self):
        os.environ.update({"IVN_LIBRARY_APP": APP, "GOR_PREFIX": "IVENDNEXT GOR", "GOR_PAGE_URL": F.PAGE,
                           "IVN_SHOPS_FILE": os.path.join(self.tmp, "shops.json")})
        try:
            app._KEPT.clear()
            out = app.lambda_handler({"httpMethod": "GET", "path": "/page.js", "headers": {}, "body": ""})
            self.assertEqual((out["statusCode"], out["headers"]["Content-Type"]), (200, "text/javascript; charset=utf-8"))
            out = app.lambda_handler({"httpMethod": "POST", "path": "/gor/menu", "headers": {},
                                      "body": json.dumps({"s": A, "t": "bad"})})
            self.assertEqual((out["statusCode"], json.loads(out["body"])), (404, {"state": "unknown"}))
        finally:
            for k in ("IVN_LIBRARY_APP", "GOR_PREFIX", "GOR_PAGE_URL", "IVN_SHOPS_FILE"):
                os.environ.pop(k, None)
            app._KEPT.clear()


class ShopApi(unittest.TestCase):
    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        hits = []

        class H(BaseHTTPRequestHandler):
            def do_GET(self):
                hits.append((self.path, self.headers.get("Authorization")))
                if self.path.startswith("/api/"):
                    self.send_response(302)
                    self.send_header("Location", f"http://127.0.0.1:{srv.server_port}/elsewhere")
                    self.end_headers()
                    return
                data = b'{"data": {"name": "C1"}}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            with self.assertRaises(app.TenantError) as e:
                app.Tenant(f"http://127.0.0.1:{srv.server_port}", "k", "s").doc("PP GOR Code", "C1")
            self.assertEqual(e.exception.code, 302)
        finally:
            srv.shutdown()
        self.assertEqual([p for p, _ in hits], ["/api/resource/PP%20GOR%20Code/C1"])


    def test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed(self):
        seen = []

        class Opener:
            def open(self, req, timeout):
                seen.append(req.full_url)
                raise app.urllib.error.URLError("stop")

        t = app.Tenant("https://shop.example.com", "k", "s")
        real = app.urllib.request.build_opener
        app.urllib.request.build_opener = lambda *h: (self.assertIn(app._NoRedirect, h), Opener())[1]
        try:
            with self.assertRaises(app.TenantError):
                t.doc("PP GOR Code", "a/b?c")
        finally:
            app.urllib.request.build_opener = real
        self.assertEqual(seen, ["https://shop.example.com/api/resource/PP%20GOR%20Code/a%2Fb%3Fc"])


if __name__ == "__main__":
    unittest.main()
