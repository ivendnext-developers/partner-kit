"""S51's service over the wire: the call checked with the check's secret, the retailer's settings read with the app's key and
kept a minute, one retailer or many (the app template's
handshake), and the down cases the till turns into its down answer.

    python3 -m unittest discover -s samples/s51_refund_rules/tests -p 'test_*.py'
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
from test_rules import CARD, CASH, DOC, ONLINE, context, line  # noqa: E402

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
    """A stand-in for the retailer's read: settings keyed by the retailer's address; records every call."""

    def __init__(self, docs=None):
        self.docs = docs if docs is not None else {"https://shop.example": DOC}
        self.calls, self.down = [], False

    def settings(self, url, key, prefix):
        self.calls.append(("settings", url, key, prefix))
        if self.down:
            raise app.ShopUnreadable("down")
        return self.docs.get(url)


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
        return self.svc.answer("/rfr/check", signed(raw, secret, ts), raw)

    def test_a_card_sales_refund_keeps_the_card_and_store_credit(self):
        self.assertEqual(self.check(context()), (200, {"verdict": "allow", "exclude_tenders": [CASH, ONLINE],
                                                       "reason": "Refunded only by the methods your rules keep for this sale."}))

    def test_the_settings_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.clock.t += 59
        self.check(context(paid_by=(CASH,)))
        self.assertEqual(self.api.calls, [("settings", "https://shop.example", "k:s", "PP RFR")])
        self.clock.t += 2
        self.check(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)

    def test_a_return_without_its_sale_reads_the_settings_alone(self):
        self.check(context(channel="none"))
        self.assertEqual([c[0] for c in self.api.calls], ["settings"])

    def test_a_sale_and_a_refund_of_nothing_read_nothing(self):
        self.assertEqual(self.check(context(stage="sale", lines=[line(qty=1)])), (200, {"verdict": "allow"}))
        self.assertEqual(self.check(context(grand=0)), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_no_settings_record_lets_every_refund_through(self):
        self.api.docs = {"https://shop.example": None}
        self.assertEqual(self.check(context()), (200, {"verdict": "allow"}))

    def test_the_check_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context())
        h = signed(raw, CHECK)
        self.assertEqual(self.svc.answer("/rfr/check", h, raw.replace(b"Credit Card", b"Cash Card")[:])[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{"v":1,"stage":"return"}}'
        self.assertEqual(self.svc.answer("/rfr/check", signed(raw, CHECK), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/rsd/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_retailer_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context())[0], 503)
        self.assertNotIn("-", self.svc.kept)

    def test_settings_that_are_not_a_record_are_a_503(self):
        self.api.docs = {"https://shop.example": []}
        self.assertEqual(self.check(context())[0], 503)

    def test_the_library_copy_never_starts_without_its_prefix(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": "ivendnext_rfr"}, store=object(), api=self.api)

    def test_the_prefix_names_the_settings_record_type(self):
        svc = app.Service(dict(ONE, RFR_PREFIX="IVENDNEXT RFR"), api=self.api, clock=self.clock)
        raw = raw_of(context())
        svc.answer("/rfr/check", signed(raw, CHECK), raw)
        self.assertIn(("settings", "https://shop.example", "k:s", "IVENDNEXT RFR"), self.api.calls)


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_rfr:sub:refunds": f"check-{n}", "user:rfr@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_rfr:sub:refunds": "check-c"}})     # no user key
        self.api = Api(docs={f"https://{self.A}": DOC, f"https://{self.B}": None})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_rfr", "RFR_PREFIX": "IVENDNEXT RFR"}, store=self.store,
                               api=self.api, clock=Clock())

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context())
        return self.svc.answer("/rfr/check", signed(raw, secret, site=site), raw)

    def test_each_retailer_is_answered_from_its_own_settings_with_its_own_key(self):
        self.assertIn("exclude_tenders", self.check("check-a", self.A)[1])     # A: the methods rule on
        self.assertEqual(self.check("check-b", self.B)[1], {"verdict": "allow"})     # B: no settings record
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

    def test_the_settings_are_kept_per_retailer(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)

    def test_a_new_key_reads_the_settings_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_rfr:sub:refunds": "check-a", "user:rfr@x": "key-a2:sec-a2"}})
        self.check("check-a", self.A)
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "settings"], ["key-a:sec-a", "key-a2:sec-a2"])


class ShopApi(unittest.TestCase):
    """``ShopApi`` against a stand-in retailer on a local port: the key, the path, a missing record, a refusal, no redirect."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []
        doc = {"data": DOC}

        class Shop(BaseHTTPRequestHandler):
            def do_GET(h):
                cls.seen.append((h.path, h.headers.get("Authorization")))
                path = h.path.partition("?")[0]
                if "Redirect" in path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20RFR%20Settings/Default")
                    h.end_headers()
                    return
                code, body = {"/api/resource/PP%20RFR%20Settings/Default": (200, doc),
                              "/api/resource/None%20Settings/Default": (404, {"exc_type": "DoesNotExistError"}),
                              "/api/resource/Locked%20Settings/Default": (403, {"exc_type": "PermissionError"}),
                              "/api/resource/Broken%20Settings/Default": (500, {"exc_type": "x"}),
                              "/api/resource/Cut%20Settings/Default": (200, None),
                              "/api/resource/Empty%20Settings/Default": (200, {"data": None}),
                              "/api/resource/Odd%20Settings/Default": (200, {"message": "ok"}),
                              }[path]
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

    def test_reads_the_default_settings_record_with_the_token(self):
        self.assertEqual(self.api.settings(self.url, "k:s", "PP RFR"), DOC)
        self.assertEqual(self.seen[-1], ("/api/resource/PP%20RFR%20Settings/Default?", "token k:s"))

    def test_no_settings_record_is_none(self):
        self.assertIsNone(self.api.settings(self.url, "k:s", "None"))

    def test_a_refusal_an_error_a_cut_answer_or_a_200_without_a_record_is_unreadable(self):
        for prefix in ("Locked", "Broken", "Cut", "Empty", "Odd"):
            with self.assertRaises(app.ShopUnreadable):
                self.api.settings(self.url, "k:s", prefix)

    def test_a_refused_key_is_named_apart_from_an_outage(self):
        with self.assertRaises(app.KeyRefused):
            self.api.settings(self.url, "k:s", "Locked")
        with self.assertRaises(app.ShopUnreadable) as e:
            self.api.settings(self.url, "k:s", "Broken")
        self.assertNotIsInstance(e.exception, app.KeyRefused)

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.settings(self.url, "k:s", "Redirect")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.settings("http://127.0.0.1:9", "k:s", "PP RFR")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_rfr:sub:refunds": "check-a", "user:rfr@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_rfr", "RFR_PREFIX": "IVENDNEXT RFR"}, store=self.store,
                          api=Api(docs={"https://shop-a.ivendnext.com": dict(DOC, store_credit="")}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context())
        for b64 in (False, True):
            out = self.entry(self.event("/rfr/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertEqual(json.loads(out["body"])["exclude_tenders"], ["Cash", "Store Credit", "Online Refund"])
        out = self.entry(self.event("/rfr/check", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed check, and one log line that carries no retailer data."""

    def test_health_a_signed_check_and_a_clean_log(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE, api=Api()), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            ctx = context(paid_by=(CASH, CARD, ONLINE))
            ctx["customer"] = "SECRET-CUSTOMER"
            raw = raw_of(ctx)
            req = urllib.request.Request(base + "/rfr/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"verdict": "allow"})
            bad = urllib.request.Request(base + "/rfr/check", data=raw, headers=signed(raw, "x"), method="POST")
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
        self.assertNotIn("ACC-PSINV-1", text)
        self.assertNotIn(CHECK, text)


if __name__ == "__main__":
    unittest.main()
