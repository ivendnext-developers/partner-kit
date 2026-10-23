"""S45 for many shops (the app template's handshake): each press checked with its own shop's secret for that button
and written with that shop's own integration key under the library's prefix, a press before Connect again answered in
words, the record API itself (the token, a table read through its record type, no redirect followed, the shop's own
words kept from its message list only), and the function entry answering the same.

    python3 -m unittest discover -s samples/s45_restaurant_back_office/tests -p 'test_*.py'
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
import backoffice as bo  # noqa: E402
import fakeshop as fs  # noqa: E402
import shops  # noqa: E402
from test_service import NOW, body, signed  # noqa: E402

APP, A, B = "ivendnext_rbo", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "RBO_PREFIX": "IVENDNEXT RBO"}


def library_tenant():
    """The same shop with the app's fields under the library's prefix."""
    t = fs.FakeTenant()
    for meta in t.items.values():
        if "pp_rbo_allergens" in meta:
            meta["ivendnext_rbo_allergens"] = meta.pop("pp_rbo_allergens")
    return t


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:issue": f"is-{n}", f"{APP}:sub:allergens": f"al-{n}", "user:rbo@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:issue": "is-c"}})     # no user key yet
        self.doors = {}
        self.svc = app.Service(LIB, store=self.store, tenants=self.door, now=lambda: NOW)

    def tearDown(self):
        bo.use_prefix("PP RBO")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = library_tenant()
            self.doors[url].key = key
        return self.doors[url]

    def press(self, secret, site, path="/press/issue", doctype="IVENDNEXT RBO Settings", names=(fs.CO,), svc=None):
        payload = body(doctype, list(names))
        h, raw = signed(payload, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", path, h, raw)

    def test_each_shop_is_issued_with_its_own_key_under_the_librarys_prefix(self):
        for secret, site in (("is-a", A), ("is-b", B)):
            self.assertIn("Issued the ingredients", self.press(secret, site)[1]["message"]["body"])
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        for d in self.doors.values():
            (se,) = d.entries.values()
            self.assertIn("ivendnext_rbo_issue", se)
            self.assertTrue(se["remarks"].startswith("IVENDNEXT RBO: "))
            self.assertIn("POST IVENDNEXT RBO Issue", d.calls)

    def test_another_buttons_secret_another_shops_an_unknown_site_and_no_site_are_refused(self):
        for secret, site in (("is-b", A), ("al-a", A), ("is-a", "shop-z.ivendnext.com"), ("is-a", None)):
            code, out = self.press(secret, site)
            self.assertEqual((code, out["error"]), (401, "the signature does not match"), (secret, site))
        self.assertFalse(any(d.issues or d.entries for d in self.doors.values()))

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("is-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["level"], out["message"]["body"]), (200, "warning", app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:issue": "is-a", "user:Administrator": "adm:sec"}))
        self.assertEqual((self.press("is-a", A)[1]["message"]["body"], self.doors), (app.NOT_SET_UP, {}))

    def test_the_allergen_check_reads_the_librarys_field(self):
        out = self.press("al-a", A, "/press/allergens", "Item", ["BURGER", "COFFEE"])[1]
        (d,) = self.doors.values()
        (chk,) = d.checks.values()
        self.assertEqual(out["open_record"]["doctype"], "IVENDNEXT RBO Allergen Check")
        self.assertIn(("BURGER", "Sesame (from BUN)"), {(r["item_code"], r["detail"]) for r in chk["lines"]})

    def test_a_shops_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        self.assertEqual(self.press("is-a", A, svc=app.Service(LIB, store=Down())), (503, {"error": "unavailable"}))


class ShopApi(unittest.TestCase):
    """``Tenant`` against a stand-in shop on a local port: the token, a table's rows read through their record type,
    no redirect followed, the shop's error type and its own message list (never its traceback), an answer cut short an
    unknown outcome."""

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
                if "Bin" in self.path:
                    return self._answer(302, headers=(("Location", "http://127.0.0.1:9/elsewhere"),))
                if "Invoice%20Item" in self.path:
                    return self._answer(200, json.dumps({"data": [{"parent": "S1"}, "not a row"]}).encode())
                self._answer(200, json.dumps({"data": {"name": "Café Co"}}).encode())

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, json.loads(self.rfile.read(n))))
                msg = json.dumps([json.dumps({"message": "Row 1: <b>BEANS</b> needed in <strong>Café</strong>"})])
                self._answer(417, json.dumps({"exc_type": "NegativeStockError", "exception": "Traceback never kept",
                                              "_server_messages": msg}).encode())

            def do_PUT(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, json.loads(self.rfile.read(n))))
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

    def test_a_record_and_a_tables_rows_are_read_with_the_token(self):
        self.assertEqual(self.t.doc("PP RBO Settings", "Café Co"), {"name": "Café Co"})
        self.assertEqual(self.t.rows("POS Invoice Item", ["parent"], [], parent="POS Invoice"), [{"parent": "S1"}])
        self.assertEqual(self.seen[0], ("GET", "/api/resource/PP%20RBO%20Settings/Caf%C3%A9%20Co", "token k:s"))
        self.assertIn("parent=POS+Invoice", self.seen[1][1])
        self.assertIn("limit_page_length=0", self.seen[1][1])

    def test_a_record_name_is_one_path_segment(self):
        self.t.doc("PP RBO Settings", "D/../../User/Administrator")
        self.assertEqual(self.seen[-1][1], "/api/resource/PP%20RBO%20Settings/D%2F..%2F..%2FUser%2FAdministrator")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.rows("Bin", ["item_code"], [])
        self.assertEqual((e.exception.code, len(self.seen)), (302, 1))

    def test_the_shops_refusal_keeps_its_type_and_its_own_words_never_its_traceback(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.create("Stock Entry", {})
        self.assertEqual((e.exception.code, e.exception.kind), (417, "NegativeStockError"))
        self.assertEqual(e.exception.said, "Row 1: BEANS needed in Café")
        self.assertNotIn("Traceback", str(e.exception) + e.exception.said)

    def test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP RBO Issue", "cut", {})
        self.assertIsNone(e.exception.code)


class Prefix(unittest.TestCase):
    def tearDown(self):
        bo.use_prefix("PP RBO")

    def test_the_record_types_and_fields_follow_the_prefix_and_the_manifest_names_them(self):
        bo.use_prefix("IVENDNEXT RBO")
        self.assertEqual((bo.dt("Settings"), bo.FIELD), ("IVENDNEXT RBO Settings", "ivendnext_rbo"))
        left = [(m.__name__, k) for m in (bo, app) for k, v in vars(m).items()
                if isinstance(v, str) and v.startswith(("pp_rbo", "PP RBO"))]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        bo.use_prefix(manifest["prefix"])
        self.assertEqual(sorted(f["fieldname"] for f in manifest["custom_fields"]),
                         [f"{bo.FIELD}_allergens", f"{bo.FIELD}_issue"])
        self.assertLessEqual({bo.dt(x) for x in ("Settings", "Issue", "Food Cost")}, {d["name"] for d in manifest["doctypes"]})


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:issue": "is-a", "user:rbo@x": "k:s"}})
        self.door = library_tenant()
        svc = app.Service(LIB, store=store, tenants=lambda url, key: self.door, now=lambda: NOW)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        bo.use_prefix("PP RBO")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        answers = []
        for b64 in (False, True):
            h, raw = signed(body("IVENDNEXT RBO Settings", [fs.CO]), "is-a")
            out = self.entry(self.event("/press/issue", raw, dict(h, **{shops.SITE_HEADER: A}), b64=b64))
            answers.append((out["statusCode"], json.loads(out["body"])["message"]["body"]))
        self.assertEqual(answers[0][0], 200)
        self.assertIn("Issued the ingredients", answers[0][1])
        self.assertEqual(answers[1], (200, "Nothing new to issue."))
        h, raw = signed(body("IVENDNEXT RBO Settings", [fs.CO]), "is-b")
        out = self.entry(self.event("/press/issue", raw, dict(h, **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.door.entries), 1)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
