"""S61 for many retailers (the app template's handshake): each press checked with its own site's secret for its own button,
read and written with that site's own integration key under the library's prefix (record types and the Item fields), a
press before the site's key arrives answered in words, the record API's errors, and the function entry answering the same.

    python3 -m unittest discover -s samples/s61_consignment_payouts/tests -p 'test_*.py'
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
import consign  # noqa: E402
import shops  # noqa: E402
from test_service import body, shop, signed  # noqa: E402

APP, A, B = "ivendnext_csg", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "CSG_PREFIX": "IVENDNEXT CSG"}


def library_shop():
    """The same retailer with its records under the library's names (built after the prefix is switched)."""
    s = shop()
    for it in s.items:
        for k in [k for k in it if k.startswith("pp_csg_")]:
            it["ivendnext_csg_" + k[len("pp_csg_"):]] = it.pop(k)
    s.rules = [{"name": "R1", "rule_name": consign.LOCK_RULE, "enabled": 1, "mode": "refuse"}]
    for p in s.payouts.values():
        p["workflow_state"] = consign.DRAFT
    return s


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:work": f"wk-{n}", f"{APP}:sub:pay": f"py-{n}", "user:csg@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:work": "wk-c"}})     # no user key yet
        self.doors, self.refuse = {}, None
        self.svc = app.Service(LIB, store=self.store, tenants=self.door)

    def tearDown(self):
        consign.use_prefix("PP CSG")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = library_shop()
            self.doors[url].refuse, self.doors[url].key = self.refuse, key
        return self.doors[url]

    def press(self, secret, site, svc=None, sub="work"):
        raw = body(doctype=consign.PAYOUT)
        h = signed(raw, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", f"/csg/{sub}", h, raw)

    def test_each_site_is_written_with_its_own_key_under_the_librarys_prefix(self):
        for secret, site in (("wk-a", A), ("wk-b", B)):
            self.assertIn("4 lines: 3 sales, 1 return.", self.press(secret, site)[1]["message"]["body"])
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        self.assertEqual((consign.PAYOUT, consign.FIELD, consign.PAID),
                         ("IVENDNEXT CSG Payout", "ivendnext_csg_", "IVENDNEXT CSG Paid"))
        for d in self.doors.values():
            self.assertEqual(len(d.writes), 1)

    def test_each_button_has_its_own_secret(self):
        self.assertEqual(self.press("wk-a", A, sub="pay")[0], 401)
        self.assertEqual(self.press("py-a", A, sub="pay")[0], 200)

    def test_another_sites_secret_an_unknown_site_and_no_site_are_refused(self):
        for secret, site in (("wk-b", A), ("wk-a", B), ("wk-a", "shop-z.ivendnext.com"), ("wk-a", None)):
            code, out = self.press(secret, site)
            self.assertEqual((code, out["error"]), (401, "the signature does not match"), (secret, site))
        self.assertEqual(sum(len(d.reads) + len(d.writes) for d in self.doors.values()), 0)

    def test_a_press_before_connect_again_is_answered_in_words_and_writes_nothing(self):
        code, out = self.press("wk-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["level"], out["message"]["body"]), (200, "warning", app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_a_site_that_refuses_the_apps_key_is_told_to_connect_again(self):
        self.refuse = (401, "AuthenticationError")
        self.assertEqual(self.press("wk-a", A)[1]["message"]["body"], app.REFUSED + app.CONNECT_AGAIN)

    def test_administrators_key_is_never_used(self):
        rec = self.store.get(A)
        self.store.put(A, dict(rec, secrets={f"{APP}:sub:work": "wk-a", "user:Administrator": "adm:sec"}))
        self.assertEqual((self.press("wk-a", A)[1]["message"]["body"], self.doors), (app.NOT_SET_UP, {}))

    def test_many_sites_without_the_librarys_prefix_refuses_to_start(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": APP}, store=self.store)

    def test_a_sites_table_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")

        self.assertEqual(self.press("wk-a", A, svc=app.Service(LIB, store=Down())), (503, {"error": "unavailable"}))


class SiteApi(unittest.TestCase):
    """``Tenant`` against a stand-in site on a local port: the token, a table read's ``parent``, the site's error type
    read (never its message), no redirect followed, an answer cut short an unknown outcome."""

    def setUp(self):
        seen = self.seen = []

        class Site(BaseHTTPRequestHandler):
            def _answer(self, code, body=b"", headers=()):
                self.send_response(code)
                for k, v in headers:
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                seen.append((self.command, self.path, self.headers.get("Authorization")))
                if "POS%20Invoice%20Item" in self.path:
                    return self._answer(302, headers=(("Location", "http://127.0.0.1:9/elsewhere"),))
                if "Item" in self.path:
                    return self._answer(200, json.dumps({"data": [{"name": "A"}]}).encode())
                self._answer(200, json.dumps({"data": {"name": "CSG-P-00001"}}).encode())

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

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Site)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.t = app.tenant_of(f"http://127.0.0.1:{self.srv.server_address[1]}", "k:s")

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_a_record_and_a_list_are_read_with_the_token(self):
        self.assertEqual(self.t.doc("PP CSG Payout", "CSG-P-00001"), {"name": "CSG-P-00001"})
        self.assertEqual(self.t.rows("Item", ["name"], []), [{"name": "A"}])
        self.assertEqual(self.seen[0], ("GET", "/api/resource/PP%20CSG%20Payout/CSG-P-00001", "token k:s"))
        self.assertIn("limit_page_length=0", self.seen[1][1])

    def test_a_tables_rows_are_read_through_their_record_type(self):
        self.t.rows("Sales Invoice Item", ["name"], [], parent="Sales Invoice")
        self.assertIn("parent=Sales+Invoice", self.seen[-1][1])

    def test_a_record_name_is_one_path_segment(self):
        self.t.doc("PP CSG Payout", "D/../../User/Administrator")
        self.assertEqual(self.seen[-1][1], "/api/resource/PP%20CSG%20Payout/D%2F..%2F..%2FUser%2FAdministrator")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.rows("POS Invoice Item", ["name"], [], parent="POS Invoice")
        self.assertEqual((e.exception.code, len(self.seen)), (302, 1))

    def test_a_stale_write_is_named_by_the_sites_error_type_and_its_message_is_dropped(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP CSG Payout", "stale", {"modified": "x"})
        self.assertEqual((e.exception.code, e.exception.kind), (417, app.STALE))
        self.assertNotIn("never shown", str(e.exception))

    def test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP CSG Payout", "cut", {})
        self.assertIsNone(e.exception.code)


class Prefix(unittest.TestCase):
    def tearDown(self):
        consign.use_prefix("PP CSG")

    def test_every_name_follows_the_prefix_and_the_manifest_names_them(self):
        consign.use_prefix("IVENDNEXT CSG")
        left = [(m.__name__, k) for m in (consign, app) for k, v in vars(m).items()
                if not k.startswith("__") and isinstance(v, str) and "/" not in v   # a file path is not a name
                and ("pp_csg" in v or "PP CSG" in v)]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        consign.use_prefix(manifest["prefix"])
        self.assertEqual(sorted(d["name"] for d in manifest["doctypes"]),
                         sorted((consign.CONSIGNOR, consign.PAYOUT, consign.LINE)))
        self.assertEqual({c["fieldname"] for c in manifest["custom_fields"]},
                         {consign.FIELD + "consignor", consign.FIELD + "share"})
        self.assertEqual({s["state"] for s in manifest["workflows"][0]["states"]},
                         {consign.DRAFT, consign.PAID, consign.CANCELLED})
        self.assertEqual(manifest["save_rules"][0]["rule_name"], consign.LOCK_RULE)
        self.assertEqual({a["record_type"] for a in manifest["desk_actions"]}, {consign.PAYOUT})


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:work": "wk-a", f"{APP}:sub:pay": "py-a",
                                                                  "user:csg@x": "k:s"}})
        self.door = None
        svc = app.Service(LIB, store=store, tenants=lambda url, key: self.door)
        self.door = library_shop()
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        consign.use_prefix("PP CSG")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        for b64 in (False, True):
            raw = body(doctype=consign.PAYOUT)
            out = self.entry(self.event("/csg/work", raw, dict(signed(raw, "wk-a"), **{shops.SITE_HEADER: A}), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertIn("4 lines", json.loads(out["body"])["message"]["body"])
        raw = body(doctype=consign.PAYOUT)
        out = self.entry(self.event("/csg/work", raw, dict(signed(raw, "py-a"), **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.door.writes), 2)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
