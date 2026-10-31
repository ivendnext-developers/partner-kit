"""S62 for many retailers (the app template's handshake): each press checked with its own site's secret, read and written
with that site's own integration key under the library's prefix (record types and the Item fields), a press before the
site's key arrives answered in words, the record API's errors (a grouped read's ``group_by`` sent), and the function
entry answering the same.

    python3 -m unittest discover -s samples/s62_liquor_excise_returns/tests -p 'test_*.py'
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
import exr  # noqa: E402
import shops  # noqa: E402
from test_service import body, shop, signed  # noqa: E402

APP, A, B = "ivendnext_exr", "shop-a.ivendnext.com", "shop-b.ivendnext.com"
LIB = {"IVN_LIBRARY_APP": APP, "EXR_PREFIX": "IVENDNEXT EXR"}


def library_shop():
    """The same retailer with its records under the library's names (built after the prefix is switched)."""
    s = shop()
    for it in s.items:
        for k in [k for k in it if k.startswith("pp_exr_")]:
            it["ivendnext_exr_" + k[len("pp_exr_"):]] = it.pop(k)
    for r in s.returns.values():
        r["workflow_state"] = exr.DRAFT
    return s


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((A, "a"), (B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{APP}:sub:work": f"wk-{n}", "user:exr@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{APP}:sub:work": "wk-c"}})     # no user key yet
        self.doors, self.refuse = {}, None
        self.svc = app.Service(LIB, store=self.store, tenants=self.door)

    def tearDown(self):
        exr.use_prefix("PP EXR")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = library_shop()
            self.doors[url].refuse, self.doors[url].key = self.refuse, key
        return self.doors[url]

    def press(self, secret, site, svc=None):
        raw = body(doctype=exr.RETURN)
        h = signed(raw, secret)
        if site:
            h[shops.SITE_HEADER] = site
        return (svc or self.svc).handle("POST", "/exr/work", h, raw)

    def test_each_site_is_written_with_its_own_key_under_the_librarys_prefix(self):
        for secret, site in (("wk-a", A), ("wk-b", B)):
            self.assertIn("3 duty classes, 5 items.", self.press(secret, site)[1]["message"]["body"])
        self.assertEqual({u: d.key for u, d in self.doors.items()},
                         {f"https://{A}": "key-a:sec-a", f"https://{B}": "key-b:sec-b"})
        self.assertEqual((exr.RETURN, exr.FIELD, exr.FILED),
                         ("IVENDNEXT EXR Return", "ivendnext_exr_", "IVENDNEXT EXR Filed"))
        for d in self.doors.values():
            self.assertEqual(len(d.writes), 1)

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
                if "Stock%20Entry" in self.path and "Ledger" not in self.path:
                    return self._answer(302, headers=(("Location", "http://127.0.0.1:9/elsewhere"),))
                if "Item" in self.path or "Ledger" in self.path:
                    return self._answer(200, json.dumps({"data": [{"name": "A"}]}).encode())
                self._answer(200, json.dumps({"data": {"name": "EXR-R-00001"}}).encode())

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
        self.assertEqual(self.t.doc("PP EXR Return", "EXR-R-00001"), {"name": "EXR-R-00001"})
        self.assertEqual(self.t.rows("Item", ["name"], []), [{"name": "A"}])
        self.assertEqual(self.seen[0], ("GET", "/api/resource/PP%20EXR%20Return/EXR-R-00001", "token k:s"))
        self.assertIn("limit_page_length=0", self.seen[1][1])
        self.assertNotIn("group_by", self.seen[1][1])

    def test_a_grouped_read_sends_its_group_by(self):
        self.t.rows("Stock Ledger Entry", ["item_code", "sum(actual_qty) as qty"], [], group_by="item_code, voucher_type")
        self.assertIn("group_by=item_code%2C+voucher_type", self.seen[-1][1])
        self.assertIn("sum%28actual_qty%29+as+qty", self.seen[-1][1])

    def test_a_record_name_is_one_path_segment(self):
        self.t.doc("PP EXR Return", "D/../../User/Administrator")
        self.assertEqual(self.seen[-1][1], "/api/resource/PP%20EXR%20Return/D%2F..%2F..%2FUser%2FAdministrator")

    def test_a_redirect_is_not_followed_and_the_key_goes_nowhere_else(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.rows("Stock Entry", ["name"], [])
        self.assertEqual((e.exception.code, len(self.seen)), (302, 1))

    def test_a_stale_write_is_named_by_the_sites_error_type_and_its_message_is_dropped(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP EXR Return", "stale", {"modified": "x"})
        self.assertEqual((e.exception.code, e.exception.kind), (417, app.STALE))
        self.assertNotIn("never shown", str(e.exception))

    def test_an_answer_cut_short_is_an_unknown_outcome_never_a_crash(self):
        with self.assertRaises(app.TenantError) as e:
            self.t.update("PP EXR Return", "cut", {})
        self.assertIsNone(e.exception.code)


class Prefix(unittest.TestCase):
    def tearDown(self):
        exr.use_prefix("PP EXR")

    def test_every_name_follows_the_prefix_and_the_manifest_names_them(self):
        exr.use_prefix("IVENDNEXT EXR")
        left = [(m.__name__, k) for m in (exr, app) for k, v in vars(m).items()
                if not k.startswith("__") and isinstance(v, str) and "/" not in v   # a file path is not a name
                and ("pp_exr" in v or "PP EXR" in v)]
        self.assertEqual(left, [])
        manifest = json.load(open(os.path.join(os.path.dirname(HERE), "manifest.json")))
        exr.use_prefix(manifest["prefix"])
        self.assertEqual(sorted(d["name"] for d in manifest["doctypes"]), sorted((exr.CLASS, exr.RETURN, exr.LINE)))
        self.assertEqual({c["fieldname"] for c in manifest["custom_fields"]},
                         {exr.FIELD + "class", exr.FIELD + "ml", exr.FIELD + "abv"})
        self.assertEqual({s["state"] for s in manifest["workflows"][0]["states"]}, {exr.DRAFT, exr.FILED})
        self.assertEqual(manifest["save_rules"][0]["rule_name"], exr.LOCK_RULE)
        self.assertEqual({a["record_type"] for a in manifest["desk_actions"]}, {exr.RETURN})
        line = {f["fieldname"]: f for f in next(d for d in manifest["doctypes"] if d["name"] == exr.LINE)["fields"]}
        self.assertEqual(line["movement"]["options"].split("\n"), list(exr.MOVEMENTS))
        unit = next(f for d in manifest["doctypes"] if d["name"] == exr.RETURN for f in d["fields"] if f["fieldname"] == "unit")
        self.assertEqual(tuple(unit["options"].split("\n")), exr.UNITS)


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        store.put(A, {"site": A, "url": f"https://{A}", "secrets": {f"{APP}:sub:work": "wk-a", "user:exr@x": "k:s"}})
        self.door = None
        svc = app.Service(LIB, store=store, tenants=lambda url, key: self.door)
        self.door = library_shop()
        self.entry = app.function.entry(lambda: svc, app.handle)

    def tearDown(self):
        exr.use_prefix("PP EXR")

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_press_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"ok": 1})
        for b64 in (False, True):
            raw = body(doctype=exr.RETURN)
            out = self.entry(self.event("/exr/work", raw, dict(signed(raw, "wk-a"), **{shops.SITE_HEADER: A}), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertIn("3 duty classes", json.loads(out["body"])["message"]["body"])
            self.door.returns["EXR-R-00001"]["lines"] = []
        raw = body(doctype=exr.RETURN)
        out = self.entry(self.event("/exr/work", raw, dict(signed(raw, "wrong"), **{shops.SITE_HEADER: A})))
        self.assertEqual(out["statusCode"], 401)
        self.assertEqual(len(self.door.writes), 2)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


if __name__ == "__main__":
    unittest.main()
