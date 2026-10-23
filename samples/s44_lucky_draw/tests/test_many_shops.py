"""S44 for many shops (the app template's handshake): each press checked with its own shop's secret for its own button,
read and written with that shop's own integration key under the library's prefix, a press before Connect again answered
in words, the record API's errors, and the function entry answering the same.

    python3 -m unittest discover -s samples/s44_lucky_draw/tests -p 'test_*.py'
"""

import base64
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
import draw  # noqa: E402
import shops  # noqa: E402
from test_service import AFTER, FakeTenant, body, campaign, signed  # noqa: E402

APP, A, B = "ivendnext_ldw", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "LDW_PREFIX": "IVENDNEXT LDW"}


def library_tenant():
    """The same shop with its campaign under the library's record type (the service reads ``draw.CAMPAIGN``)."""
    return FakeTenant()


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:count": f"ct-{n}", f"{APP}:sub:draw": f"dr-{n}", "user:ldw@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:count": "ct-c"}})     # no user key yet
        self.doors, self.refuse = {}, None
        self.svc = app.Service(LIB, store=self.store, tenants=self.door, now=AFTER)

    def tearDown(self):
        draw.use_prefix("PP LDW")

    def door(self, url, key):
        """Each shop's own record API, reached with the key that shop handed over (one stand-in per shop)."""
        if url not in self.doors:
            self.doors[url] = library_tenant()
            self.doors[url].refuse, self.doors[url].key = self.refuse, key
        return self.doors[url]

    def press(self, secret, site, svc=None, sub="count"):
        raw = body()
        h = signed(raw, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", f"/press/{sub}", h, raw)

    def test_each_shop_is_written_with_its_own_key_under_the_librarys_prefix(self):
        for secret, site in (("ct-a", A), ("ct-b", B)):
            self.assertEqual(self.press(secret, site)[1]["message"]["body"], "4 sales by 3 customers: 9 entries so far.")
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        self.assertEqual(draw.CAMPAIGN, "IVENDNEXT LDW Campaign")
        for d in self.doors.values():
            self.assertEqual(len(d.writes), 1)

    def test_each_button_has_its_own_secret(self):
        self.assertEqual(self.press("ct-a", A, sub="draw")[0], 401)
        self.assertIn("Drew 2 winners", self.press("dr-a", A, sub="draw")[1]["message"]["body"])

    def test_another_shops_secret_an_unknown_site_and_no_site_are_refused(self):
        for secret, site in (("ct-b", A), ("ct-a", B), ("ct-a", "shop-z.ivendnext.com"), ("ct-a", None)):
            code, out = self.press(secret, site)
            self.assertEqual((code, out["error"]), (401, "the signature does not match"), (secret, site))
        self.assertEqual(sum(len(d.writes) for d in self.doors.values()), 0)

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("ct-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["level"], out["message"]["body"]), (200, "warning", app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_a_shop_that_refuses_the_apps_user_is_told_so_in_words(self):
        self.refuse = 403
        self.assertEqual(self.press("ct-a", A)[1]["message"]["body"], app.REFUSED + app.CONNECT_AGAIN)

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:count": "ct-a", "user:Administrator": "adm:sec"}))
        self.assertEqual((self.press("ct-a", A)[1]["message"]["body"], self.doors), (app.NOT_SET_UP, {}))

    def test_many_shops_without_the_librarys_prefix_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": APP}, store=self.store)

    def test_a_shops_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        self.assertEqual(self.press("ct-a", A, svc=app.Service(LIB, store=Down())), (503, {"error": "unavailable"}))


class ShopApi(unittest.TestCase):
    """``Tenant`` against a stand-in shop on a local port: the token, a list read's query, the shop's error type read
    (never its message), no redirect followed, an answer cut short an unknown outcome."""

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
                if "POS%20Invoice" in self.path:
                    return self._answer(302, headers=(("Location", "http://127.0.0.1:9/elsewhere"),))
                if "Customer%20Group" in self.path:
                    return self._answer(200, json.dumps({"data": [{"name": "Members"}]}).encode())
                self._answer(200, json.dumps({"data": {"name": "Default"}}).encode())

            def do_PUT(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, json.loads(self.rfile.read(n))))
                if "stale" in self.path:
                    return self._answer(417, json.dumps({"exc_type": "TimestampMismatchError",
                                                         "exception": "a message never shown"}).encode())
                self.send_response(200)
                self.send_header("Content-Length", "100")
                self.end_headers()
                self.wfile.write(b'{"data": ')        # the connection closes before the rest

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.t = app.tenant_of(f"http://127.0.0.1:{self.srv.server_address[1]}", "k:s")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_record_and_a_list_are_read_with_the_token(self):
        self.assertEqual(self.t.doc("PP LDW Campaign", "Default"), {"name": "Default"})
        self.assertEqual(self.t.rows("Customer Group", ["name"], []), [{"name": "Members"}])
        self.assertEqual(self.seen[0], ("GET", "/api/resource/PP%20LDW%20Campaign/Default", "token k:s"))
        self.assertIn("limit_page_length=0", self.seen[1][1])

    def test_a_record_name_is_one_path_segment(self):
        self.t.doc("PP LDW Campaign", "D/../../User/Administrator")
        self.assertEqual(self.seen[-1][1], "/api/resource/PP%20LDW%20Campaign/D%2F..%2F..%2FUser%2FAdministrator")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.rows("POS Invoice", ["name"], [])
        self.assertEqual((e.exception.code, len(self.seen)), (302, 1))

    def test_a_stale_write_is_named_by_the_shops_error_type_and_its_message_is_dropped(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP LDW Campaign", "stale", {"modified": "x"})
        self.assertEqual((e.exception.code, e.exception.kind), (417, app.STALE))
        self.assertNotIn("never shown", str(e.exception))

    def test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP LDW Campaign", "cut", {})
        self.assertIsNone(e.exception.code)


class Prefix(unittest.TestCase):
    def tearDown(self):
        draw.use_prefix("PP LDW")

    def test_the_record_type_follows_the_prefix_and_the_manifest_names_it(self):
        draw.use_prefix("IVENDNEXT LDW")
        self.assertEqual(draw.CAMPAIGN, "IVENDNEXT LDW Campaign")
        left = [(m.__name__, k) for m in (draw, app) for k, v in vars(m).items()
                if isinstance(v, str) and v.startswith(("pp_ldw", "PP LDW"))]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        draw.use_prefix(manifest["prefix"])
        self.assertIn(draw.CAMPAIGN, [d["name"] for d in manifest["doctypes"]])
        self.assertEqual({a["record_type"] for a in manifest["desk_actions"]}, {draw.CAMPAIGN})


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:count": "ct-a", f"{APP}:sub:draw": "dr-a",
                                                                  "user:ldw@x": "k:s"}})
        self.door = library_tenant()
        svc = app.Service(LIB, store=store, tenants=lambda url, key: self.door, now=AFTER)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        draw.use_prefix("PP LDW")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        bodies = []
        for b64 in (False, True):
            raw = body()
            out = self.entry(self.event("/press/draw", raw, dict(signed(raw, "dr-a"), **{shops.SITE_HEADER: A}), b64=b64))
            bodies.append((out["statusCode"], json.loads(out["body"])["message"]["body"][:15]))
        self.assertEqual(bodies, [(200, "Drew 2 winners "), (200, "Already drawn o")])
        raw = body()
        out = self.entry(self.event("/press/draw", raw, dict(signed(raw, "ct-a"), **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.door.writes), 1)        # one draw, once

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
