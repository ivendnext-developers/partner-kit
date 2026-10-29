"""S55 for many shops (the app template's handshake): each press checked with its own shop's secret for that button and
answered with that shop's own key for the app's user, under the library's prefix; a press before the shop's key arrives
answered in words; the shop's API itself (the token, the door's verbs on the till's partner API, no redirect followed,
the shop's own words kept, never its traceback); and the function entry answering the same.

    python3 -m unittest discover -s samples/s55_front_of_house/tests -p 'test_*.py'
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
import fakeshop as fs  # noqa: E402
import foh  # noqa: E402
import shops  # noqa: E402
from test_service import NOW, body, signed  # noqa: E402

APP, A, B = "ivendnext_foh", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "FOH_PREFIX": "IVENDNEXT FOH"}
RES = "IVENDNEXT FOH Reservation"


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:book": f"bk-{n}", f"{APP}:sub:seat": f"st-{n}", "user:foh@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:book": "bk-c"}})     # no user key yet
        self.doors = {}
        self.svc = app.Service(LIB, store=self.store, tenants=self.door, now=lambda: NOW)

    def tearDown(self):
        foh.use_prefix("PP FOH")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = fs.FakeTenant([fs.booking("R1", "19:00:00", status="Requested")])
            self.doors[url].key = key
        return self.doors[url]

    def press(self, secret, site, path="/press/book", doctype=RES, name="R1", svc=None):
        h, raw = signed(body(doctype, [name]), secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", path, h, raw)

    def test_each_shop_is_answered_with_its_own_key_under_the_librarys_prefix(self):
        for secret, site in (("bk-a", A), ("bk-b", B)):
            self.assertIn("is booked", self.press(secret, site)[1]["message"]["body"])
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        for d in self.doors.values():
            self.assertIn(f"PUT {RES}", d.calls)
            self.assertIn("LIST IVENDNEXT FOH Store", d.calls)

    def test_another_buttons_secret_another_shops_an_unknown_site_and_no_site_are_refused(self):
        for secret, site in (("bk-b", A), ("st-a", A), ("bk-a", "shop-z.ivendnext.com"), ("bk-a", None)):
            code, out = self.press(secret, site)
            self.assertEqual((code, out["error"]), (401, "the signature does not match"), (secret, site))
        self.assertFalse(any(d.calls for d in self.doors.values()))

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("bk-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["level"], out["message"]["body"]), (200, "warning", app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:book": "bk-a", "user:Administrator": "adm:sec"}))
        self.assertEqual((self.press("bk-a", A)[1]["message"]["body"], self.doors), (app.NOT_SET_UP, {}))

    def test_a_shops_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        self.assertEqual(self.press("bk-a", A, svc=app.Service(LIB, store=Down())), (503, {"error": "unavailable"}))


class ShopApi(unittest.TestCase):
    """``Tenant`` against a stand-in shop on a local port: the token, the door's verbs as POST and GET on the till's
    partner API, a record name as one path segment, no redirect followed, the shop's error type and its own words."""

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
                if "Elsewhere" in self.path:
                    return self._answer(302, headers=(("Location", "http://127.0.0.1:9/elsewhere"),))
                if "floor_status" in self.path:
                    return self._answer(200, json.dumps({"message": {"store": "S", "places": []}}).encode())
                self._answer(200, json.dumps({"data": {"name": "R1"}}).encode())

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, json.loads(self.rfile.read(n))))
                msg = json.dumps([json.dumps({"message": "That place is <b>switched off</b>. Pick another."})])
                self._answer(417, json.dumps({"exc_type": "CheckRequestError", "exception": "Traceback never kept",
                                              "_server_messages": msg}).encode())

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.t = app.tenant_of(f"http://127.0.0.1:{self.srv.server_address[1]}", "k:s")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_record_and_the_floor_are_read_with_the_token(self):
        self.assertEqual(self.t.doc("PP FOH Reservation", "R1"), {"name": "R1"})
        self.assertEqual(self.t.call("floor_status", query={"store": "Bistro - BC"}), {"store": "S", "places": []})
        self.assertEqual(self.seen[0], ("GET", "/api/resource/PP%20FOH%20Reservation/R1", "token k:s"))
        self.assertEqual(self.seen[1][1], "/api/method/ivendnext_mpos.api.v1.floor_status?store=Bistro+-+BC")

    def test_a_record_name_is_one_path_segment(self):
        self.t.doc("PP FOH Reservation", "D/../../User/Administrator")
        self.assertEqual(self.seen[-1][1], "/api/resource/PP%20FOH%20Reservation/D%2F..%2F..%2FUser%2FAdministrator")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.doc("Elsewhere", "x")
        self.assertEqual((e.exception.code, len(self.seen)), (302, 1))

    def test_the_doors_refusal_keeps_its_type_and_its_own_words_never_its_traceback(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.call("check_open", {"store": "S", "key": "k"})
        self.assertEqual(self.seen[0][:2], ("POST", "/api/method/ivendnext_mpos.api.v1.check_open"))
        self.assertEqual(self.seen[0][2], {"store": "S", "key": "k"})
        self.assertEqual((e.exception.code, e.exception.kind, e.exception.refused), (417, "CheckRequestError", True))
        self.assertEqual(e.exception.said, "That place is switched off. Pick another.")
        self.assertNotIn("Traceback", str(e.exception) + e.exception.said)

    def test_no_answer_is_an_unknown_outcome_never_a_refusal(self):
        e = app.TenantError("check_open -> TimeoutError")
        self.assertFalse(e.refused)
        self.assertFalse(app.TenantError("x", 502).refused)


class Prefix(unittest.TestCase):
    def tearDown(self):
        foh.use_prefix("PP FOH")

    def test_the_record_types_follow_the_prefix_and_the_manifest_names_them(self):
        foh.use_prefix("IVENDNEXT FOH")
        self.assertEqual(foh.dt("Reservation"), "IVENDNEXT FOH Reservation")
        left = [(m.__name__, k) for m in (foh, app) for k, v in vars(m).items()
                if isinstance(v, str) and v.startswith(("pp_foh", "PP FOH"))]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        foh.use_prefix(manifest["prefix"])
        self.assertLessEqual({foh.dt(x) for x in ("Settings", "Store", "Reservation", "Waitlist Entry")},
                             {d["name"] for d in manifest["doctypes"]})


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:seat": "st-a", "user:foh@x": "k:s"}})
        self.door = fs.FakeTenant([fs.booking("R1", "19:00:00")])
        svc = app.Service(LIB, store=store, tenants=lambda url, key: self.door, now=lambda: NOW)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        foh.use_prefix("PP FOH")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        answers = []
        for b64 in (False, True):
            h, raw = signed(body(RES, ["R1"]), "st-a")
            out = self.entry(self.event("/press/seat", raw, dict(h, **{shops.SITE_HEADER: A}), b64=b64))
            answers.append((out["statusCode"], json.loads(out["body"])["message"]["body"]))
        self.assertEqual(answers[0][0], 200)
        self.assertIn("its check CHK-0001 is open", answers[0][1])
        self.assertIn("already seated", answers[1][1])
        h, raw = signed(body(RES, ["R1"]), "st-b")
        out = self.entry(self.event("/press/seat", raw, dict(h, **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.door.checks), 1)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
