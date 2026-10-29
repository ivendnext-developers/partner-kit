"""S46's service over the wire: the call checked with the check's secret, the shop's rules and group tree read at the
same time with the app's key and kept a minute, one shop or many (the app template's handshake), and the down cases the
till turns into its down answer.

    python3 -m unittest discover -s samples/s46_payment_method_rules/tests -p 'test_*.py'
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
from test_rules import RECORDS, TREE_ROWS, context  # noqa: E402

CHECK = "check-secret-1"
ONE = {"IVN_CHECK_SECRET": CHECK, "IVN_SHOP_URL": "https://shop.example", "IVN_SHOP_KEY": "k:s"}


def raw_of(ctx):
    return json.dumps({"point": "check/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}
    if site:
        h[shops.SITE_HEADER] = site
    return h


class Api:
    """A stand-in for the shop's reads: rules and trees from dicts keyed by the shop's address; records every call."""

    def __init__(self, rules=None, trees=None):
        self.rules_by = rules if rules is not None else {"https://shop.example": RECORDS}
        self.trees_by = trees if trees is not None else {"https://shop.example": TREE_ROWS}
        self.calls, self.down, self.tree_down = [], False, False

    def rules(self, url, key, prefix):
        self.calls.append(("rules", url, key, prefix))
        if self.down:
            raise app.ShopUnreadable("down")
        return self.rules_by.get(url)

    def tree(self, url, key):
        self.calls.append(("tree", url, key))
        if self.down or self.tree_down:
            raise app.ShopUnreadable("down")
        return self.trees_by.get(url, [])


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class OneShop(unittest.TestCase):
    def setUp(self):
        self.api, self.clock = Api(), Clock()
        self.svc = app.Service(ONE, api=self.api, clock=self.clock)

    def check(self, ctx, secret=CHECK, ts=None):
        raw = raw_of(ctx)
        return self.svc.answer("/pmr/check", signed(raw, secret, ts), raw)

    def test_a_ruled_group_has_its_methods_left_out(self):
        code, out = self.check(context(group="Talabat"))
        self.assertEqual((code, out["verdict"], out["reason"]), (200, "allow", "Talabat customers pay with Talabat."))
        self.assertNotIn("Talabat", out["exclude_tenders"])
        self.assertIn("Cash", out["exclude_tenders"])

    def test_a_group_takes_the_rule_above_it_from_the_shops_tree(self):
        self.assertEqual(self.check(context(group="Gold accounts"))[1]["exclude_tenders"], ["Gift Certificate"])
        self.assertEqual(self.check(context(group="Retail"))[1]["exclude_tenders"], ["On Account"])

    def test_the_rules_and_the_tree_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.clock.t += 59
        self.check(context(group="Talabat"))
        self.assertEqual(sorted(self.api.calls), [("rules", "https://shop.example", "k:s", "PP PMR"),
                                                  ("tree", "https://shop.example", "k:s")])
        self.clock.t += 2
        self.check(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "tree"]), 2)

    def test_a_refund_reads_nothing(self):
        self.assertEqual(self.check(context(group="Talabat", stage="return")), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_a_sale_with_no_offered_method_reads_nothing(self):
        self.assertEqual(self.check(context(group="Talabat", offered=[])), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_the_check_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context(group="Retail"))
        h = signed(raw, CHECK)
        self.assertEqual(self.svc.answer("/pmr/check", h, raw.replace(b"Retail", b"Talaba"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(self.svc.answer("/pmr/check", signed(raw, CHECK), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/cpn/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_shop_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context(group="Talabat"))[0], 503)

    def test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules(self):
        self.api.tree_down = True
        self.assertEqual(self.check(context(group="Gold accounts"))[0], 503)
        self.assertNotIn("-", self.svc.kept)           # nothing half-read is kept

    def test_rules_that_are_not_records_are_a_503(self):
        self.api.rules_by = {"https://shop.example": None}
        self.assertEqual(self.check(context())[0], 503)

    def test_the_prefix_names_the_rule_record_type(self):
        svc = app.Service(dict(ONE, PMR_PREFIX="IVENDNEXT PMR"), api=self.api, clock=self.clock)
        raw = raw_of(context())
        svc.answer("/pmr/check", signed(raw, CHECK), raw)
        self.assertIn(("rules", "https://shop.example", "k:s", "IVENDNEXT PMR"), self.api.calls)


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_pmr:sub:methods": f"check-{n}", "user:pmr@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_pmr:sub:methods": "check-c"}})     # no user key
        self.api = Api(rules={f"https://{self.A}": RECORDS, f"https://{self.B}": []},
                       trees={f"https://{self.A}": TREE_ROWS, f"https://{self.B}": TREE_ROWS})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_pmr", "PMR_PREFIX": "IVENDNEXT PMR"}, store=self.store,
                               api=self.api, clock=Clock())

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context(group="Talabat"))
        return self.svc.answer("/pmr/check", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_rules_with_its_own_key(self):
        self.assertIn("exclude_tenders", self.check("check-a", self.A)[1])           # A: Talabat ruled
        self.assertEqual(self.check("check-b", self.B)[1], {"verdict": "allow"})     # B: no rules
        seen = sorted({c[1:3] for c in self.api.calls})
        self.assertEqual(seen, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_another_shops_secret_is_refused(self):
        self.assertEqual(self.check("check-b", self.A)[0], 401)
        self.assertEqual(self.check("check-a", self.B)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.check("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.check("check-a", None)[0], 401)

    def test_a_shop_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.check("check-c", "shop-c.ivendnext.com")[0], 503)

    def test_the_rules_are_kept_per_shop(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_a_new_key_reads_the_rules_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_pmr:sub:methods": "check-a", "user:pmr@x": "key-a2:sec-a2"}})
        self.check("check-a", self.A)
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "rules"], ["key-a:sec-a", "key-a2:sec-a2"])


class ShopApi(unittest.TestCase):
    """``ShopApi`` against a stand-in shop on a local port: the key, the paths, a refusal, an error, no redirect."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []

        class Shop(BaseHTTPRequestHandler):
            def do_GET(h):
                cls.seen.append((h.path, h.headers.get("Authorization")))
                path, q = h.path.split("?", 1)
                if "Redirect" in path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20PMR%20Rule?{q}")
                    h.end_headers()
                    return
                listed = "/api/resource/Listed%20Rule"
                if path in (listed, "/api/resource/Odd%20Rule"):   # a retailer on 1.0.x: no min_sale on its rows
                    fields = json.loads(dict(urllib.parse.parse_qsl(q))["fields"])
                    if path != listed or "methods.min_sale" in fields:
                        path = "/api/resource/Missing%20Field"
                code, body = {"/api/resource/PP%20PMR%20Rule": (200, {"data": RECORDS}),
                              listed: (200, {"data": RECORDS}),
                              "/api/resource/Missing%20Field": (417, {"exc_type": "DataError"}),
                              "/api/resource/Customer%20Group": (200, {"data": TREE_ROWS}),
                              "/api/resource/Gone%20Rule": (404, {"exc_type": "DoesNotExistError"}),
                              "/api/resource/Locked%20Rule": (403, {"exc_type": "PermissionError"}),
                              "/api/resource/Broken%20Rule": (500, {"exc_type": "x"}),
                              "/api/resource/Cut%20Rule": (200, None)}[path]
                if body is None:                 # an answer cut short: more promised than sent
                    h.send_response(code)
                    h.send_header("Content-Length", "100")
                    h.end_headers()
                    h.wfile.write(b'{"dat')
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

    def test_reads_every_switched_on_rule_with_its_methods_and_the_token(self):
        self.assertEqual(self.api.rules(self.url, "k:s", "PP PMR"), RECORDS)
        path, auth = self.seen[-1]
        self.assertEqual(auth, "token k:s")
        args = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
        self.assertEqual((json.loads(args["filters"]), args["limit_page_length"]), ([["enabled", "=", 1]], "0"))
        self.assertEqual(json.loads(args["fields"]), list(app.payrules.RULE_FIELDS))
        self.assertIn("methods.mode_of_payment", json.loads(args["fields"]))

    def test_a_retailer_on_the_listed_version_is_read_again_without_the_amount(self):
        start = len(self.seen)
        self.assertEqual(self.api.rules(self.url, "k:s", "Listed"), RECORDS)
        asked = [json.loads(dict(urllib.parse.parse_qsl(p.split("?", 1)[1]))["fields"]) for p, _ in self.seen[start:]]
        self.assertEqual(asked, [list(app.payrules.RULE_FIELDS), list(app.payrules.RULE_FIELDS_LISTED)])

    def test_a_field_refused_twice_is_unreadable_and_never_a_key_refused(self):
        start = len(self.seen)
        with self.assertRaises(app.ShopUnreadable) as e:
            self.api.rules(self.url, "k:s", "Odd")
        self.assertNotIsInstance(e.exception, app.KeyRefused)
        self.assertEqual(len(self.seen) - start, 2)     # one read again, never a loop

    def test_reads_the_whole_group_tree(self):
        self.assertEqual(self.api.tree(self.url, "k:s"), TREE_ROWS)
        args = dict(urllib.parse.parse_qsl(self.seen[-1][0].split("?", 1)[1]))
        self.assertEqual((json.loads(args["fields"]), args["limit_page_length"]), (["name", "lft", "rgt"], "0"))

    def test_a_refusal_an_error_or_a_404_is_unreadable(self):
        for prefix in ("Locked", "Broken", "Gone"):
            with self.assertRaises(app.ShopUnreadable):
                self.api.rules(self.url, "k:s", prefix)

    def test_a_refused_key_is_named_apart_from_an_outage(self):
        with self.assertRaises(app.KeyRefused):
            self.api.rules(self.url, "k:s", "Locked")
        for prefix in ("Broken", "Gone"):
            with self.assertRaises(app.ShopUnreadable) as e:
                self.api.rules(self.url, "k:s", prefix)
            self.assertNotIsInstance(e.exception, app.KeyRefused)

    def test_a_cut_answer_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.rules(self.url, "k:s", "Cut")

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.rules(self.url, "k:s", "Redirect")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.rules("http://127.0.0.1:9", "k:s", "PP PMR")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_pmr:sub:methods": "check-a", "user:pmr@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_pmr"}, store=self.store,
                          api=Api(rules={"https://shop-a.ivendnext.com": RECORDS},
                                  trees={"https://shop-a.ivendnext.com": TREE_ROWS}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context(group="Talabat"))
        for b64 in (False, True):
            out = self.entry(self.event("/pmr/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertIn("Cash", json.loads(out["body"])["exclude_tenders"])
        out = self.entry(self.event("/pmr/check", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed check, and one log line that carries no shop data."""

    def test_health_a_signed_check_and_a_clean_log(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE, api=Api()), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            raw = raw_of(context(group="Talabat", customer="SECRET-CUSTOMER"))
            req = urllib.request.Request(base + "/pmr/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertIn("exclude_tenders", json.loads(r.read()))
            bad = urllib.request.Request(base + "/pmr/check", data=raw, headers=signed(raw, "x"), method="POST")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(e.exception.code, 401)
            e.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()
        text = log.getvalue()
        self.assertIn('"status": 200', text)
        self.assertNotIn("SECRET-CUSTOMER", text)
        self.assertNotIn(CHECK, text)


if __name__ == "__main__":
    unittest.main()
