"""S32's service over the wire: the call checked with the check's secret, the shop's rules read with the app's key and kept
a minute, the first purchase counted live, one shop or many (the app template's handshake), and the down cases the till
turns into its down answer.

    python3 -m unittest discover -s samples/s32_coupon_rules/tests -p 'test_*.py'
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
from test_rules import RECORDS, context  # noqa: E402

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
    """A stand-in for the shop's reads: rules and counts from dicts keyed by the shop's address; records every call."""

    def __init__(self, rules=None, sales=None):
        self.rules_by = rules if rules is not None else {"https://shop.example": RECORDS}
        self.sales_by = sales or {}                    # url -> {(doctype, customer): n}
        self.calls, self.down, self.refuse, self.refuse_count = [], False, False, False

    def _gate(self):
        if self.refuse:
            raise app.KeyRefused("403")
        if self.down:
            raise app.ShopUnreadable("down")

    def rules(self, url, key, prefix):
        self.calls.append(("rules", url, key, prefix))
        self._gate()
        return self.rules_by.get(url)

    def count(self, url, key, doctype, filters):
        self.calls.append(("count", url, key, doctype, json.dumps(filters)))
        self._gate()
        if self.refuse_count:            # the role reads the rules but was never given read on the sales
            raise app.KeyRefused("403")
        customer = next(f[2] for f in filters if f[0] == "customer")
        return self.sales_by.get(url, {}).get((doctype, customer), 0)


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
        return self.svc.answer("/cpn/check", signed(raw, secret, ts), raw)

    def test_a_returning_customer_is_refused_a_first_purchase_coupon(self):
        self.api.sales_by = {"https://shop.example": {("POS Invoice", "CUST-1"): 2}}
        code, out = self.check(context(["WELCOME10"]))
        self.assertEqual((code, out["verdict"]), (200, "refuse"))
        self.assertIn("has bought before", out["reason"])

    def test_a_new_customer_is_counted_at_the_till_and_in_the_back_office(self):
        self.assertEqual(self.check(context(["WELCOME10"])), (200, {"verdict": "allow"}))
        counts = sorted((c for c in self.api.calls if c[0] == "count"), key=lambda c: c[3])
        self.assertEqual([c[3] for c in counts], ["POS Invoice", "Sales Invoice"])
        self.assertEqual(json.loads(counts[0][4]), [["customer", "=", "CUST-1"], ["docstatus", "=", 1], ["is_return", "=", 0]])
        self.assertEqual(json.loads(counts[1][4]), [["customer", "=", "CUST-1"], ["docstatus", "=", 1], ["is_return", "=", 0],
                                                    ["is_consolidated", "=", 0]])

    def test_a_back_office_sale_counts_as_bought_before(self):
        self.api.sales_by = {"https://shop.example": {("Sales Invoice", "CUST-1"): 1}}
        self.assertEqual(self.check(context(["WELCOME10"]))[1]["verdict"], "refuse")

    def test_both_ledgers_are_counted_at_once_and_added(self):
        self.api.sales_by = {"https://shop.example": {("POS Invoice", "CUST-1"): 1}}
        self.assertEqual(self.check(context(["WELCOME10"]))[1]["verdict"], "refuse")
        self.assertEqual(sorted(c[3] for c in self.api.calls if c[0] == "count"), ["POS Invoice", "Sales Invoice"])

    def test_the_count_alone_refused_refuses_the_coupon_in_words(self):
        self.api.refuse_count = True
        self.assertEqual(self.check(context(["WELCOME10"])), (200, {"verdict": "refuse", "reason": app.KEY_REFUSED}))
        self.assertEqual(self.check(context(["STAFF15"], group="Staff")), (200, {"verdict": "allow"}))   # no count needed

    def test_a_group_coupon_is_judged_from_the_rules(self):
        self.assertEqual(self.check(context(["STAFF15"], group="Retail"))[1]["verdict"], "refuse")
        self.assertEqual(self.check(context(["STAFF15"], group="Staff"))[1]["verdict"], "allow")

    def test_a_sale_with_no_coupon_reads_nothing(self):
        self.assertEqual(self.check(context([])), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_the_check_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(["WELCOME10"]), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context(["STAFF15"], group="Staff"))
        h = signed(raw, CHECK)
        self.assertEqual(self.svc.answer("/cpn/check", h, raw.replace(b"Staff", b"Staf2"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(self.svc.answer("/cpn/check", signed(raw, CHECK), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/tgr/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_rules_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context(["STAFF15"], group="Staff"))
        self.clock.t += 59
        self.check(context(["STAFF15"], group="Staff"))
        rules = [c for c in self.api.calls if c[0] == "rules"]
        self.assertEqual(rules, [("rules", "https://shop.example", "k:s", "PP CPN")])
        self.clock.t += 2
        self.check(context(["STAFF15"], group="Staff"))
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_the_count_is_never_kept(self):
        self.check(context(["WELCOME10"]))
        self.api.sales_by = {"https://shop.example": {("POS Invoice", "CUST-1"): 1}}
        self.assertEqual(self.check(context(["WELCOME10"]))[1]["verdict"], "refuse")

    def test_the_shop_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context(["STAFF15"]))[0], 503)

    def test_the_count_down_is_a_503_never_an_allow(self):
        self.check(context(["STAFF15"], group="Staff"))        # the rules are kept
        self.api.down = True
        self.assertEqual(self.check(context(["WELCOME10"]))[0], 503)

    def test_a_refused_key_refuses_a_ruled_coupon_in_words(self):
        self.api.refuse = True
        self.assertEqual(self.check(context(["WELCOME10"])), (200, {"verdict": "refuse", "reason": app.KEY_REFUSED}))
        self.assertTrue(len(app.KEY_REFUSED) <= 140)

    def test_rules_that_are_not_records_are_a_503(self):
        self.api.rules_by = {"https://shop.example": None}
        self.assertEqual(self.check(context(["WELCOME10"]))[0], 503)

    def test_the_prefix_names_the_rule_record_type(self):
        svc = app.Service(dict(ONE, CPN_PREFIX="IVENDNEXT CPN"), api=self.api, clock=self.clock)
        raw = raw_of(context(["STAFF15"], group="Staff"))
        svc.answer("/cpn/check", signed(raw, CHECK), raw)
        self.assertEqual(self.api.calls[-1][3], "IVENDNEXT CPN")


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_cpn:sub:coupons": f"check-{n}", "user:cpn@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_cpn:sub:coupons": "check-c"}})     # no user key
        self.api = Api(rules={f"https://{self.A}": RECORDS, f"https://{self.B}": []},
                       sales={f"https://{self.A}": {("POS Invoice", "CUST-1"): 1}})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_cpn", "CPN_PREFIX": "IVENDNEXT CPN"}, store=self.store,
                               api=self.api, clock=Clock())

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context(["WELCOME10"]))
        return self.svc.answer("/cpn/check", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_rules_with_its_own_key(self):
        self.assertEqual(self.check("check-a", self.A)[1]["verdict"], "refuse")        # A: WELCOME10 ruled, CUST-1 bought
        self.assertEqual(self.check("check-b", self.B)[1]["verdict"], "allow")         # B: no rules
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

    def test_a_shop_without_its_key_and_no_coupon_is_still_allowed(self):
        raw = raw_of(context([]))
        self.assertEqual(self.svc.answer("/cpn/check", signed(raw, "check-c", site="shop-c.ivendnext.com"), raw),
                         (200, {"verdict": "allow"}))

    def test_the_rules_are_kept_per_shop(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_a_new_key_reads_the_rules_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_cpn:sub:coupons": "check-a", "user:cpn@x": "key-a2:sec-a2"}})
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
                args = dict(urllib.parse.parse_qsl(q))
                if path.endswith("get_count"):
                    who = json.loads(args["filters"])[0][2]
                    code, body = {"CUST-1": (200, {"message": 4}), "CUST-0": (200, {"message": 0}),
                                  "BOOL": (200, {"message": True}), "TEXT": (200, {"message": "4"}),
                                  "DENIED": (403, {"exc_type": "PermissionError"}),
                                  "CUT": (200, None)}[who]
                elif "Redirect" in path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20CPN%20Rule?{q}")
                    h.end_headers()
                    return
                else:
                    code, body = {"/api/resource/PP%20CPN%20Rule": (200, {"data": RECORDS}),
                                  "/api/resource/Gone%20Rule": (404, {"exc_type": "DoesNotExistError"}),
                                  "/api/resource/Locked%20Rule": (401, {"exc_type": "AuthenticationError"}),
                                  "/api/resource/Broken%20Rule": (500, {"exc_type": "x"})}[path]
                if body is None:                 # an answer cut short: more promised than sent
                    h.send_response(code)
                    h.send_header("Content-Length", "100")
                    h.end_headers()
                    h.wfile.write(b'{"mess')
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

    def test_reads_every_switched_on_rule_with_the_token(self):
        self.assertEqual(self.api.rules(self.url, "k:s", "PP CPN"), RECORDS)
        path, auth = self.seen[-1]
        self.assertEqual(auth, "token k:s")
        args = dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))
        self.assertEqual((json.loads(args["filters"]), args["limit_page_length"]), ([["enabled", "=", 1]], "0"))
        self.assertEqual(json.loads(args["fields"]), list(app.coupons.RULE_FIELDS))

    def test_counts_through_the_shops_ivendnext_name(self):
        self.assertEqual(self.api.count(self.url, "k:s", "POS Invoice", [["customer", "=", "CUST-1"]]), 4)
        path, auth = self.seen[-1]
        self.assertTrue(path.startswith("/api/method/ivendnext_mpos.api.v1.get_count?"))
        self.assertEqual(dict(urllib.parse.parse_qsl(path.split("?", 1)[1]))["doctype"], "POS Invoice")
        self.assertEqual(self.api.count(self.url, "k:s", "POS Invoice", [["customer", "=", "CUST-0"]]), 0)

    def test_a_count_that_is_not_a_whole_number_is_unreadable(self):
        for who in ("BOOL", "TEXT"):
            with self.assertRaises(app.ShopUnreadable):
                self.api.count(self.url, "k:s", "POS Invoice", [["customer", "=", who]])

    def test_a_refusal_is_key_refused_and_an_error_or_404_is_unreadable(self):
        with self.assertRaises(app.KeyRefused):
            self.api.rules(self.url, "k:s", "Locked")
        with self.assertRaises(app.KeyRefused):
            self.api.count(self.url, "k:s", "POS Invoice", [["customer", "=", "DENIED"]])
        for prefix in ("Broken", "Gone"):
            with self.assertRaises(app.ShopUnreadable) as e:
                self.api.rules(self.url, "k:s", prefix)
            self.assertNotIsInstance(e.exception, app.KeyRefused)

    def test_a_cut_answer_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.count(self.url, "k:s", "POS Invoice", [["customer", "=", "CUT"]])

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.rules(self.url, "k:s", "Redirect")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.rules("http://127.0.0.1:9", "k:s", "PP CPN")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_cpn:sub:coupons": "check-a", "user:cpn@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_cpn"}, store=self.store,
                          api=Api(rules={"https://shop-a.ivendnext.com": RECORDS}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context(["STAFF15"], group="Retail"))
        for b64 in (False, True):
            out = self.entry(self.event("/cpn/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual((out["statusCode"], json.loads(out["body"])["verdict"]), (200, "refuse"))
        out = self.entry(self.event("/cpn/check", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
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
            raw = raw_of(context(["STAFF15"], customer="SECRET-CUSTOMER", group="Retail"))
            req = urllib.request.Request(base + "/cpn/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            bad = urllib.request.Request(base + "/cpn/check", data=raw, headers=signed(raw, "x"), method="POST")
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
