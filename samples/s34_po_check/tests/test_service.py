"""S34's service over the wire: the call checked with the subscription's secret, one shop or many (the app template's
handshake), and the cases the shop turns into its down answer (a 4xx or 5xx: ``refuse`` in this manifest).

    python3 -m unittest discover -s samples/s34_po_check/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import io
import json
import os
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service"), str(HERE)]
import app  # noqa: E402
import shops  # noqa: E402
from test_po_check import FIELD, body, context  # noqa: E402

SECRET = "check-secret-1"
ONE = {"IVN_CHECK_SECRET": SECRET}


def raw_of(ctx):
    return json.dumps(body(ctx), sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}
    if site:
        h[shops.SITE_HEADER] = site
    return h


class OneShop(unittest.TestCase):
    def setUp(self):
        self.svc = app.Service(ONE)

    def post(self, ctx=None, secret=SECRET, ts=None, path=app.ROUTE, raw=None):
        raw = raw if raw is not None else raw_of(ctx or context())
        return self.svc.handle("POST", path, signed(raw, secret, ts), raw)

    def test_the_three_answers(self):
        self.assertEqual(self.post(context(supplier="Acme Supplies"))[1]["verdict"], "refuse")
        self.assertEqual(self.post(context(minor=900000))[1]["verdict"], "approve")
        self.assertEqual(self.post(), (200, {"verdict": "fill", "fields": {FIELD: "ERP-PO-9912"}}))

    def test_a_wrong_secret_or_an_old_call_is_401(self):
        self.assertEqual(self.post(secret="other")[0], 401)
        self.assertEqual(self.post(ts=time.time() - 3600)[0], 401)

    def test_a_call_this_app_cannot_read_is_400(self):
        self.assertEqual(self.post(raw=b"not json")[0], 400)
        self.assertEqual(self.post(context(supplier=""))[0], 400)

    def test_an_unknown_route_is_404_and_health_is_200(self):
        self.assertEqual(self.post(path="/other")[0], 404)
        self.assertEqual(self.svc.handle("GET", "/health", {}, b""), (200, {"status": "ok"}))

    def test_a_body_too_large_is_413(self):
        self.assertEqual(self.svc.handle("POST", app.ROUTE, {}, None)[0], 413)

    def test_the_prefix_names_the_fill_field(self):
        svc = app.Service(dict(ONE, POC_PREFIX="ivendnext_poc"))
        raw = raw_of(context())
        self.assertEqual(svc.handle("POST", app.ROUTE, signed(raw, SECRET), raw)[1]["fields"], {"ivendnext_poc_erp_number": "ERP-PO-9912"})


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {"ivendnext_poc:sub:po_check": f"check-{n}"}})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_poc"}, store=self.store)

    def post(self, secret, site):
        raw = raw_of(context())
        return self.svc.handle("POST", app.ROUTE, signed(raw, secret, site=site), raw)

    def test_each_shop_signs_with_its_own_secret(self):
        self.assertEqual(self.post("check-a", self.A)[0], 200)
        self.assertEqual(self.post("check-b", self.B)[0], 200)
        self.assertEqual(self.post("check-b", self.A)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.post("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.post("check-a", None)[0], 401)

    def test_a_store_that_does_not_answer_is_a_503(self):
        class Down:
            def get(self, site):
                raise OSError("down")
        self.svc.store = Down()
        self.assertEqual(self.post("check-a", self.A)[0], 503)


class Wire(unittest.TestCase):
    def test_a_real_call_over_http_and_one_log_line_without_the_body(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE), 0, log=log)
        import threading
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            raw = raw_of(context(supplier="Acme Supplies"))
            req = urllib.request.Request(f"http://127.0.0.1:{srv.server_address[1]}{app.ROUTE}", data=raw,
                                         headers=signed(raw, SECRET), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(req.full_url, data=raw, headers=signed(raw, "x"), method="POST"), timeout=5)
            self.assertEqual(e.exception.code, 401)
        finally:
            srv.shutdown()
        lines = [json.loads(x) for x in log.getvalue().splitlines()]
        self.assertEqual([x["status"] for x in lines], [200, 401])
        self.assertNotIn("Acme", log.getvalue())


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(ONE)
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {app.ROUTE: (app.SUB, SECRET)}

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
