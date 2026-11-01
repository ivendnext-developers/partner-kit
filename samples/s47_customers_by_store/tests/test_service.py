"""S47's service over the wire: the call checked with the capture's secret, the shop's rules and group tree read at the
same time with the app's key and kept a minute, one shop or many (the app template's handshake), and the down cases the
till turns into its down answer.

    python3 -m unittest discover -s samples/s47_customers_by_store/tests -p 'test_*.py'
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

SECRET = "capture-secret-1"
ONE = {"IVN_CAPTURE_SECRET": SECRET, "IVN_SHOP_URL": "https://shop.example", "IVN_SHOP_KEY": "k:s"}


def raw_of(ctx):
    return json.dumps({"point": "capture/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


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

    def select(self, ctx, secret=SECRET, ts=None):
        raw = raw_of(ctx)
        return self.svc.answer("/cbs/select", signed(raw, secret, ts), raw)

    def test_a_customer_outside_their_stores_is_taken_off_in_words(self):
        code, out = self.select(context(group="Trade accounts", store="Bulawayo - CL"))
        self.assertEqual((code, out["verdict"]), (200, "refuse"))
        self.assertTrue(out["reason"].startswith("Customers in Trade accounts buy only at "))
        self.assertEqual(self.select(context(group="Trade accounts", store="Sandton - CL")), (200, {"verdict": "allow"}))

    def test_a_group_takes_the_rule_above_it_from_the_shops_tree(self):
        self.assertEqual(self.select(context(group="Gold trade", store="Bulawayo - CL"))[1]["verdict"], "refuse")
        self.assertEqual(self.select(context(group="Retail", store="Bulawayo - CL"))[1], {"verdict": "allow"})

    def test_the_rules_and_the_tree_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.select(context())
        self.clock.t += 59
        self.select(context(group="Trade accounts"))
        self.assertEqual(sorted(self.api.calls), [("rules", "https://shop.example", "k:s", "PP CBS"),
                                                  ("tree", "https://shop.example", "k:s")])
        self.clock.t += 2
        self.select(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "tree"]), 2)

    def test_the_select_takes_only_its_own_secret(self):
        self.assertEqual(self.select(context(), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.select(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context(group="Retail"))
        h = signed(raw, SECRET)
        self.assertEqual(self.svc.answer("/cbs/select", h, raw.replace(b"Retail", b"Staff!"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400_and_reads_nothing(self):
        for ctx in ({}, dict(context(), event="customer_add")):
            raw = json.dumps({"point": "capture/1", "context": ctx}).encode()
            self.assertEqual(self.svc.answer("/cbs/select", signed(raw, SECRET), raw)[0], 400)
        self.assertEqual(self.api.calls, [])

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/pmr/check", signed(raw, SECRET), raw)[0], 404)

    def test_the_shop_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.select(context(group="Trade accounts", store="Bulawayo - CL"))[0], 503)

    def test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules(self):
        self.api.tree_down = True                       # a group with its own rule: only the tree's read can make this a 503
        self.assertEqual(self.select(context(group="Trade accounts", store="Bulawayo - CL"))[0], 503)
        self.assertNotIn("-", self.svc.kept)           # nothing half-read is kept

    def test_a_group_the_kept_tree_does_not_know_is_a_503_and_is_read_again(self):
        self.select(context())
        self.assertEqual(self.select(context(group="Made a minute ago", store="Bulawayo - CL"))[0], 503)
        self.assertNotIn("-", self.svc.kept)
        self.select(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_rules_that_are_not_records_are_a_503(self):
        self.api.rules_by = {"https://shop.example": None}
        self.assertEqual(self.select(context())[0], 503)

    def test_the_prefix_names_the_rule_record_type(self):
        svc = app.Service(dict(ONE, CBS_PREFIX="IVENDNEXT CBS"), api=self.api, clock=self.clock)
        raw = raw_of(context())
        svc.answer("/cbs/select", signed(raw, SECRET), raw)
        self.assertIn(("rules", "https://shop.example", "k:s", "IVENDNEXT CBS"), self.api.calls)


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_cbs:sub:on_select": f"check-{n}", "user:cbs@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_cbs:sub:on_select": "check-c"}})     # no user key
        self.api = Api(rules={f"https://{self.A}": RECORDS, f"https://{self.B}": []},
                       trees={f"https://{self.A}": TREE_ROWS, f"https://{self.B}": TREE_ROWS})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_cbs", "CBS_PREFIX": "IVENDNEXT CBS"}, store=self.store,
                               api=self.api, clock=Clock())

    def select(self, secret, site, ctx=None):
        raw = raw_of(ctx or context(group="Trade accounts", store="Bulawayo - CL"))
        return self.svc.answer("/cbs/select", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_rules_with_its_own_key(self):
        self.assertEqual(self.select("check-a", self.A)[1]["verdict"], "refuse")     # A: Trade accounts ruled
        self.assertEqual(self.select("check-b", self.B)[1], {"verdict": "allow"})     # B: no rules
        seen = sorted({c[1:3] for c in self.api.calls})
        self.assertEqual(seen, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_another_shops_secret_is_refused(self):
        self.assertEqual(self.select("check-b", self.A)[0], 401)
        self.assertEqual(self.select("check-a", self.B)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.select("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.select("check-a", None)[0], 401)

    def test_a_shop_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.select("check-c", "shop-c.ivendnext.com")[0], 503)

    def test_the_rules_are_kept_per_shop(self):
        self.select("check-a", self.A)
        self.select("check-b", self.B)
        self.select("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_a_new_key_reads_the_rules_again(self):
        self.select("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_cbs:sub:on_select": "check-a", "user:cbs@x": "key-a2:sec-a2"}})
        self.select("check-a", self.A)
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
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20CBS%20Rule?{q}")
                    h.end_headers()
                    return
                code, body = {"/api/resource/PP%20CBS%20Rule": (200, {"data": RECORDS}),
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

    def test_reads_every_switched_on_rule_with_its_places_and_the_token(self):
        self.assertEqual(self.api.rules(self.url, "k:s", "PP CBS"), RECORDS)
        path, auth = self.seen[-1]
        self.assertEqual(auth, "token k:s")
        args = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
        self.assertEqual((json.loads(args["filters"]), args["limit_page_length"]), ([["enabled", "=", 1]], "0"))
        self.assertEqual(json.loads(args["fields"]), list(app.storerules.RULE_FIELDS))
        self.assertIn("places.store", json.loads(args["fields"]))
        self.assertIn("places.pos_profile", json.loads(args["fields"]))

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
            self.api.rules("http://127.0.0.1:9", "k:s", "PP CBS")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_cbs:sub:on_select": "check-a", "user:cbs@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_cbs"}, store=self.store,
                          api=Api(rules={"https://shop-a.ivendnext.com": RECORDS},
                                  trees={"https://shop-a.ivendnext.com": TREE_ROWS}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_select_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context(group="Trade accounts", store="Bulawayo - CL"))
        for b64 in (False, True):
            out = self.entry(self.event("/cbs/select", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertEqual(json.loads(out["body"])["verdict"], "refuse")
        out = self.entry(self.event("/cbs/select", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed select, and one log line that carries no shop or customer data."""

    def test_health_a_signed_select_and_a_clean_log(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE, api=Api()), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            raw = raw_of(context(group="Trade accounts", store="Bulawayo - CL", customer="SECRET-CUSTOMER"))
            req = urllib.request.Request(base + "/cbs/select", data=raw, headers=signed(raw, SECRET), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            bad = urllib.request.Request(base + "/cbs/select", data=raw, headers=signed(raw, "x"), method="POST")
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
        self.assertNotIn(SECRET, text)
        self.assertNotIn("+263771234567", text)


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(ONE)
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {app.ROUTE: (app.KEY, SECRET)}

    def call(self, path, raw, secret, test=True):
        import base64, hashlib, hmac, time
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        return self.svc.handle("POST", path, h, raw)

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and refused
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
