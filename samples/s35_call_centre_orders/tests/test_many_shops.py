"""S35 for many shops (the app template's handshake): each press checked with its own shop's secret and written with
that shop's own integration key under the library's field name, a press before the shop's key arrives answered in words, the
shop's refusals named in words, and the function entry answering the same.

    python3 -m unittest discover -s samples/s35_call_centre_orders/tests -p 'test_*.py'
"""

import base64
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import app  # noqa: E402
import route  # noqa: E402
import shops  # noqa: E402
from test_service import FakeTenant, body, order, signed  # noqa: E402

APP, A, B = "ivendnext_cco", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "CCO_PREFIX": "IVENDNEXT CCO"}
LF = "ivendnext_cco_store"


def tree():
    return {"Cairo": {"parent_territory": "", LF: "Cairo Store - S"}, "Maadi": {"parent_territory": "Cairo"}}


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:route": f"route-{n}", "user:cco@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:route": "route-c"}})     # no user key yet
        self.doors, self.refuse = {}, None
        self.svc = self.copy()

    def tearDown(self):
        route.use_prefix("PP CCO")

    def door(self, url, key):
        """Each shop's own record API, reached with the key that shop handed over (one stand-in per shop)."""
        if url not in self.doors:
            self.doors[url] = FakeTenant(tree=tree(), refuse=self.refuse)
            self.doors[url].key = key
        return self.doors[url]

    def copy(self):
        return app.Service(LIB, store=self.store, tenants=self.door)

    def press(self, secret, site, svc=None):
        raw = body()
        h = signed(raw, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", "/press/route", h, raw)

    def test_each_shop_is_written_with_its_own_key_under_the_librarys_field(self):
        self.assertEqual(self.press("route-a", A)[1]["message"]["title"], "Sent to store")
        self.assertEqual(self.press("route-b", B)[1]["message"]["title"], "Sent to store")
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        for d in self.doors.values():           # Maadi has no store under the library's field: Cairo's, read by that name
            self.assertEqual(d.writes[0][1]["set_warehouse"], "Cairo Store - S")

    def test_another_shops_secret_an_unknown_site_and_no_site_are_refused(self):
        for secret, site in (("route-b", A), ("route-a", B), ("route-a", "shop-z.ivendnext.com"), ("route-a", None)):
            code, out = self.press(secret, site)
            self.assertEqual((code, out["error"]), (401, "the signature does not match"), (secret, site))
        self.assertEqual(sum(len(d.writes) for d in self.doors.values()), 0)

    def test_a_shop_whose_secret_changed_is_accepted_with_the_previous_one_while_it_moves(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets=dict(rec["secrets"], **{f"{APP}:sub:route": "route-a2"}),
                               previous={f"{APP}:sub:route": "route-a"}))
        self.assertEqual(self.press("route-a", A)[0], 200)

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("route-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["level"], out["message"]["body"]), (200, "warning", app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_a_shop_that_refuses_the_apps_user_is_told_so_in_words(self):
        self.refuse = 403
        code, out = self.press("route-a", A)
        self.assertEqual((code, out["message"]["body"]), (200, app.REFUSED + app.CONNECT_AGAIN))

    def test_a_shop_that_does_not_answer_is_a_502_so_the_user_checks_the_record(self):
        self.refuse = 500
        self.assertEqual(self.press("route-a", A)[0], 502)

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:route": "route-a", "user:Administrator": "adm:sec"}))
        code, out = self.press("route-a", A)
        self.assertEqual((code, out["message"]["body"], self.doors), (200, app.NOT_SET_UP, {}))

    def test_many_shops_without_the_librarys_prefix_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": APP}, store=self.store)

    def test_a_shops_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        svc = app.Service(LIB, store=Down())
        self.assertEqual(self.press("route-a", A, svc=svc), (503, {"error": "unavailable"}))

    def test_the_handshake_and_health_are_answered(self):
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"ok": 1}))
        code, out = self.svc.handle("POST", shops.CONNECT, {shops.SITE_HEADER: A}, b'{"site": "%s", "key": "x", "secrets": {}}' % A.encode())
        self.assertEqual((code, out), (403, {"refused": "key_form"}))


class ShopApi(unittest.TestCase):
    """``Tenant`` against a stand-in shop on a local port: the token, the shop's error type read (never its message),
    the stale write named, no redirect followed, an answer cut short an unknown outcome."""

    def setUp(self):
        seen = self.seen = []

        class Shop(BaseHTTPRequestHandler):
            def _answer(self, code, body=b"", headers=()):
                self.send_response(code)
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                seen.append((self.command, self.path, self.headers.get("Authorization")))
                if "Territory" in self.path:
                    return self._answer(302, headers=(("Location", "http://127.0.0.1:9/elsewhere"),))
                self._answer(200, json.dumps({"data": {"name": "SO-1"}}).encode())

            def do_PUT(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, json.loads(self.rfile.read(n))))
                if "stale" in self.path:
                    return self._answer(417, json.dumps({"exc_type": "TimestampMismatchError",
                                                         "exception": "a message never shown"}).encode())
                if "cut" in self.path:
                    self.send_response(200)
                    self.send_header("Content-Length", "100")
                    self.end_headers()
                    return self.wfile.write(b'{"data": ')        # the connection closes before the rest
                self._answer(417, b"not json")

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.t = app.tenant_of(f"http://127.0.0.1:{self.srv.server_address[1]}", "k:s")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_the_order_is_read_with_the_token_at_its_own_address(self):
        self.assertEqual(self.t.order("SO-1"), {"name": "SO-1"})
        self.assertEqual(self.seen, [("GET", "/api/resource/Sales%20Order/SO-1", "token k:s")])

    def test_a_record_name_is_one_path_segment(self):
        self.t.order("SO/../../User/Administrator")       # a name a person typed never reaches another record's address
        self.assertEqual(self.seen[-1][1], "/api/resource/Sales%20Order/SO%2F..%2F..%2FUser%2FAdministrator")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.territory("Cairo")
        self.assertEqual(e.exception.code, 302)
        self.assertEqual(len(self.seen), 1)

    def test_a_stale_write_is_named_by_the_shops_error_type_and_its_message_is_dropped(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.write("stale", {"modified": "x"})
        self.assertEqual((e.exception.code, e.exception.kind), (417, app.STALE))
        self.assertNotIn("never shown", str(e.exception))

    def test_an_error_body_that_is_not_json_has_no_type(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.write("other", {})
        self.assertEqual((e.exception.code, e.exception.kind), (417, ""))

    def test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.write("cut", {})
        self.assertIsNone(e.exception.code)


class Prefix(unittest.TestCase):
    def tearDown(self):
        route.use_prefix("PP CCO")

    def test_the_field_follows_the_prefix_and_the_manifest_names_it(self):
        route.use_prefix("IVENDNEXT CCO")
        self.assertEqual(route.FIELD, LF)
        left = [(m.__name__, k) for m in (route, app) for k, v in vars(m).items()
                if isinstance(v, str) and v.startswith("pp_cco")]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        route.use_prefix(manifest["prefix"])
        self.assertEqual([f["fieldname"] for f in manifest["custom_fields"] if f["dt"] == "Territory"], [route.FIELD])


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:route": "route-a", "user:cco@x": "k:s"}})
        self.door = FakeTenant([order(territory="Maadi")], tree=tree())
        svc = app.Service(LIB, store=store, tenants=lambda url, key: self.door)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        route.use_prefix("PP CCO")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        titles = []
        for b64 in (False, True):
            raw = body()
            out = self.entry(self.event("/press/route", raw, dict(signed(raw, "route-a"), **{shops.SITE_HEADER: A}), b64=b64))
            titles.append((out["statusCode"], json.loads(out["body"])["message"]["title"]))
        self.assertEqual(titles, [(200, "Sent to store"), (200, "Already with its store")])
        raw = body()
        out = self.entry(self.event("/press/route", raw, dict(signed(raw, "route-b"), **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.door.writes), 1)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
