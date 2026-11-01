"""S50's service over the wire: the call checked with the check's secret, the retailer's rules and group tree read at
the same time with the app's key and kept a minute, one retailer or many (the app template's handshake), and the down cases
the till turns into its down answer.

    python3 -m unittest discover -s samples/s50_required_sale_details/tests -p 'test_*.py'
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
    """A stand-in for the retailer's reads: rules and trees from dicts keyed by the retailer's address; records every call."""

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
        return self.svc.answer("/rsd/check", signed(raw, secret, ts), raw)

    def test_a_needed_detail_left_empty_is_refused_in_words(self):
        code, out = self.check(context())
        self.assertEqual((code, out), (200, {"verdict": "refuse", "reason": "Customers in Account customers need Purchase "
                                                                             "order number. Fill in the sale's details, then Pay."}))

    def test_the_detail_filled_lets_the_sale_go_on(self):
        self.assertEqual(self.check(context(attrs={"Purchase order number": "PO-4471"})), (200, {"verdict": "allow"}))

    def test_a_group_takes_the_rule_above_it_from_the_retailers_tree(self):
        self.assertEqual(self.check(context(group="Gold accounts"))[1]["verdict"], "refuse")
        self.assertEqual(self.check(context(group="Retail"))[1], {"verdict": "allow"})

    def test_the_rules_and_the_tree_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.clock.t += 59
        self.check(context(group="Insured"))
        self.assertEqual(sorted(self.api.calls), [("rules", "https://shop.example", "k:s", "PP RSD"),
                                                  ("tree", "https://shop.example", "k:s")])
        self.clock.t += 2
        self.check(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "tree"]), 2)

    def test_a_refund_reads_nothing(self):
        self.assertEqual(self.check(context(group="Insured", stage="return")), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_the_check_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context(group="Retail"))
        h = signed(raw, CHECK)
        self.assertEqual(self.svc.answer("/rsd/check", h, raw.replace(b"Retail", b"Talaba"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(self.svc.answer("/rsd/check", signed(raw, CHECK), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/cpn/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_retailer_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context(group="Insured"))[0], 503)

    def test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules(self):
        self.api.tree_down = True
        self.assertEqual(self.check(context(group="Gold accounts"))[0], 503)
        self.assertNotIn("-", self.svc.kept)           # nothing half-read is kept

    def test_rules_that_are_not_records_are_a_503(self):
        self.api.rules_by = {"https://shop.example": None}
        self.assertEqual(self.check(context())[0], 503)

    def test_the_prefix_names_the_rule_record_type(self):
        svc = app.Service(dict(ONE, RSD_PREFIX="IVENDNEXT RSD"), api=self.api, clock=self.clock)
        raw = raw_of(context())
        svc.answer("/rsd/check", signed(raw, CHECK), raw)
        self.assertIn(("rules", "https://shop.example", "k:s", "IVENDNEXT RSD"), self.api.calls)


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_rsd:sub:details": f"check-{n}", "user:rsd@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_rsd:sub:details": "check-c"}})     # no user key
        self.api = Api(rules={f"https://{self.A}": RECORDS, f"https://{self.B}": []},
                       trees={f"https://{self.A}": TREE_ROWS, f"https://{self.B}": TREE_ROWS})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_rsd", "RSD_PREFIX": "IVENDNEXT RSD"}, store=self.store,
                               api=self.api, clock=Clock())

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context())
        return self.svc.answer("/rsd/check", signed(raw, secret, site=site), raw)

    def test_each_retailer_is_answered_from_its_own_rules_with_its_own_key(self):
        self.assertEqual(self.check("check-a", self.A)[1]["verdict"], "refuse")      # A: account customers ruled
        self.assertEqual(self.check("check-b", self.B)[1], {"verdict": "allow"})     # B: no rules
        seen = sorted({c[1:3] for c in self.api.calls})
        self.assertEqual(seen, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_another_retailers_secret_is_refused(self):
        self.assertEqual(self.check("check-b", self.A)[0], 401)
        self.assertEqual(self.check("check-a", self.B)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.check("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.check("check-a", None)[0], 401)

    def test_a_retailer_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.check("check-c", "shop-c.ivendnext.com")[0], 503)

    def test_the_rules_are_kept_per_retailer(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_a_new_key_reads_the_rules_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_rsd:sub:details": "check-a", "user:rsd@x": "key-a2:sec-a2"}})
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
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20RSD%20Rule?{q}")
                    h.end_headers()
                    return
                code, body = {"/api/resource/PP%20RSD%20Rule": (200, {"data": RECORDS}),
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

    def test_reads_every_switched_on_rule_with_its_details_and_the_token(self):
        self.assertEqual(self.api.rules(self.url, "k:s", "PP RSD"), RECORDS)
        path, auth = self.seen[-1]
        self.assertEqual(auth, "token k:s")
        args = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
        self.assertEqual((json.loads(args["filters"]), args["limit_page_length"]), ([["enabled", "=", 1]], "0"))
        self.assertEqual(json.loads(args["fields"]), list(app.details.RULE_FIELDS))
        self.assertIn("details.sale_attribute", json.loads(args["fields"]))

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
            self.api.rules("http://127.0.0.1:9", "k:s", "PP RSD")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_rsd:sub:details": "check-a", "user:rsd@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_rsd"}, store=self.store,
                          api=Api(rules={"https://shop-a.ivendnext.com": RECORDS},
                                  trees={"https://shop-a.ivendnext.com": TREE_ROWS}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context())
        for b64 in (False, True):
            out = self.entry(self.event("/rsd/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertEqual(json.loads(out["body"])["verdict"], "refuse")
        out = self.entry(self.event("/rsd/check", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
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
            raw = raw_of(context(customer="SECRET-CUSTOMER", attrs={"Purchase order number": "SECRET-PO"}))
            req = urllib.request.Request(base + "/rsd/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"verdict": "allow"})
            bad = urllib.request.Request(base + "/rsd/check", data=raw, headers=signed(raw, "x"), method="POST")
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
        self.assertNotIn("SECRET-PO", text)
        self.assertNotIn(CHECK, text)


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(ONE)
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {app.ROUTE: (app.KEY, CHECK)}

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
