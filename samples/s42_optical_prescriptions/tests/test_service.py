"""S42's service over the wire: the route checked with its own secret, the shop's settings, item groups and items' marks
read with the app's key and kept a minute, the customer's prescriptions read fresh (three fields) only when a line needs
one, one shop or many (the app template's handshake), and the down cases the till turns into its down answer.

    python3 -m unittest discover -s samples/s42_optical_prescriptions/tests -p 'test_*.py'
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
from test_rules import GROUPS, ITEMS, NOW, RX_CL, RX_CL_OLD, RX_SPECS, SETTINGS, context, line  # noqa: E402

CHECK = "check-secret-1"
URL = "https://shop.example"
ONE = {"IVN_CHECK_SECRET": CHECK, "IVN_SHOP_URL": URL, "IVN_SHOP_KEY": "k:s"}


def raw_of(ctx, point="check/1"):
    return json.dumps({"point": point, "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}
    if site:
        h[shops.SITE_HEADER] = site
    return h


class Api:
    """A stand-in for the shop's reads, keyed by the shop's address; records every call."""

    def __init__(self):
        self.settings_by, self.groups_by, self.items_by = {URL: SETTINGS}, {URL: GROUPS}, {URL: ITEMS}
        self.rx_by = {(URL, "Ana Lopez"): [RX_SPECS, RX_CL], (URL, "Ben Old"): [RX_CL_OLD]}
        self.calls, self.down = [], False

    def _gate(self):
        if self.down:
            raise app.ShopUnreadable("down")

    def settings(self, url, key, prefix):
        self.calls.append(("settings", url, key, prefix))
        self._gate()
        return self.settings_by.get(url)

    def groups(self, url, key, prefix):
        self.calls.append(("groups", url, key, prefix))
        self._gate()
        return self.groups_by.get(url)

    def items(self, url, key, prefix, codes):
        self.calls.append(("items", url, key, tuple(codes)))
        self._gate()
        return [i for i in self.items_by.get(url, []) if i["name"] in codes]

    def prescriptions(self, url, key, prefix, customer):
        self.calls.append(("prescriptions", url, key, prefix, customer))
        self._gate()
        return self.rx_by.get((url, customer), [])


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class OneShop(unittest.TestCase):
    def setUp(self):
        self.api, self.clock = Api(), Clock()
        self.svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: NOW)

    def check(self, ctx, secret=CHECK, ts=None):
        raw = raw_of(ctx)
        return self.svc.answer("/opt/check", signed(raw, secret, ts), raw)

    def test_a_customer_with_both_prescriptions_in_date_is_allowed(self):
        ctx = context([line("SV-LENS", "Spectacle lenses"), line("ACUVUE-30", "Contact lenses", n=2)])
        self.assertEqual(self.check(ctx), (200, {"verdict": "allow"}))

    def test_a_walk_in_or_unknown_customer_is_refused_naming_the_line(self):
        code, out = self.check(context([line("ACUVUE-30", "Contact lenses", n=3)], customer="Walk In"))
        self.assertEqual((code, out["verdict"]), (200, "refuse"))
        self.assertTrue(out["reason"].startswith("Line 3: ACUVUE-30 needs a contact lens prescription for this customer."))
        self.assertEqual(self.api.calls[-1], ("prescriptions", URL, "k:s", "PP OPT", "Walk In"))

    def test_an_expired_prescription_names_the_day(self):
        out = self.check(context([line("ACUVUE-30", "Contact lenses")], customer="Ben Old"))[1]
        self.assertIn("ran out on 10 Jan 2026", out["reason"])

    def test_nothing_needing_a_prescription_reads_no_prescription(self):
        self.assertEqual(self.check(context([line("FRAME-1", "Frames"), line("PLANO", "Plano lenses")])),
                         (200, {"verdict": "allow"}))
        self.assertNotIn("prescriptions", [c[0] for c in self.api.calls])

    def test_prescriptions_are_read_at_every_pay_never_kept(self):
        self.check(context())
        self.api.rx_by[(URL, "Ana Lopez")] = []                 # the prescription deleted in Desk
        self.assertEqual(self.check(context())[1]["verdict"], "refuse")
        self.assertEqual(len([c for c in self.api.calls if c[0] == "prescriptions"]), 2)

    def test_the_shops_hours_decide_today(self):
        self.api.rx_by[(URL, "Ana Lopez")] = [dict(RX_SPECS, valid_until="2026-10-23")]
        late = NOW + 9.5 * 3600                                # 21:30 UTC: the 24th in Dubai, the 23rd in UTC
        svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: late)
        raw = raw_of(context())
        self.assertEqual(svc.answer("/opt/check", signed(raw, CHECK), raw)[1]["verdict"], "refuse")
        self.api.settings_by[URL] = None
        svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: late)
        self.assertEqual(svc.answer("/opt/check", signed(raw, CHECK), raw)[1], {"verdict": "allow"})

    def test_a_variant_is_judged_by_its_templates_mark_read_in_a_second_step(self):
        out = self.check(context([line("TORIC-2", "Frames")], customer="Walk In"))[1]
        self.assertIn("needs a contact lens prescription", out["reason"])
        self.assertEqual([c[3] for c in self.api.calls if c[0] == "items"], [("TORIC-2",), ("TORIC",)])

    def test_a_refund_is_allowed_without_reading_anything(self):
        self.assertEqual(self.check(context([line("SV-LENS", "Spectacle lenses", -2)], stage="return")), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.calls, [])

    def test_a_returned_lens_line_reads_no_prescription(self):
        ctx = context([line("SV-LENS", "Spectacle lenses", -1), line("FRAME-1", "Frames", n=2)], stage="return")
        self.assertEqual(self.check(ctx), (200, {"verdict": "allow"}))
        self.assertNotIn("prescriptions", [c[0] for c in self.api.calls])

    def test_only_its_own_secret_is_taken(self):
        self.assertEqual(self.check(context(), secret="another")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/opt/check", signed(raw, CHECK), raw.replace(b"SV-LENS", b"SV-LENZ"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(self.svc.answer("/opt/check", signed(raw, CHECK), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/age/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_settings_groups_and_items_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.clock.t += 59
        self.check(context())
        self.assertEqual([c for c in self.api.calls if c[0] != "prescriptions"],
                         [("settings", URL, "k:s", "PP OPT"), ("groups", URL, "k:s", "PP OPT"), ("items", URL, "k:s", ("SV-LENS",))])
        self.check(context([line("SV-LENS", "Spectacle lenses"), line("FRAME-1", "Frames")]))
        self.assertEqual([c for c in self.api.calls if c[0] == "items"][-1], ("items", URL, "k:s", ("FRAME-1",)))
        self.clock.t += 2
        self.check(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)
        self.assertEqual([c for c in self.api.calls if c[0] == "items"][-1], ("items", URL, "k:s", ("SV-LENS",)))

    def test_the_shop_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context())[0], 503)

    def test_prescriptions_that_lack_their_fields_are_a_503_not_a_refusal(self):
        self.api.rx_by[(URL, "Ana Lopez")] = [{"name": "OPT-RX-00001"}]     # a bare SELECT right: names only
        self.assertEqual(self.check(context())[0], 503)

    def test_items_without_their_mark_are_a_503_not_unmarked(self):
        self.api.items_by[URL] = [{"name": i["name"], "variant_of": i.get("variant_of")} for i in ITEMS]   # names only
        self.assertEqual(self.check(context([line("SUN-RX", "Frames")], customer="Walk In"))[0], 503)

    def test_an_item_the_shop_does_not_return_is_a_503(self):
        self.assertEqual(self.check(context([line("NEW-LENS", "Spectacle lenses")]))[0], 503)

    def test_groups_that_are_not_records_are_a_503(self):
        self.api.groups_by[URL] = None
        self.assertEqual(self.check(context())[0], 503)

    def test_the_prefix_names_the_fields_and_the_record_types(self):
        self.api.groups_by[URL] = [{k.replace("pp_opt_", "ivendnext_opt_"): v for k, v in g.items()} for g in GROUPS]
        self.api.items_by[URL] = [{k.replace("pp_opt_", "ivendnext_opt_"): v for k, v in i.items()} for i in ITEMS]
        svc = app.Service(dict(ONE, OPT_PREFIX="IVENDNEXT OPT"), api=self.api, clock=self.clock, now=lambda: NOW)
        raw = raw_of(context(customer="Walk In"))
        self.assertEqual(svc.answer("/opt/check", signed(raw, CHECK), raw)[1]["verdict"], "refuse")
        self.assertEqual({c[3] for c in self.api.calls if c[0] in ("settings", "groups", "prescriptions")}, {"IVENDNEXT OPT"})


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_opt:sub:check": f"check-{n}", "user:opt@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_opt:sub:check": "check-c"}})     # no user key
        self.api = Api()
        for site, mark in ((self.A, "Spectacles"), (self.B, "")):
            u = f"https://{site}"
            groups = [dict(g, pp_opt_needs=mark) if g["name"] == "Spectacle lenses" else g for g in GROUPS]
            self.api.settings_by[u], self.api.groups_by[u], self.api.items_by[u] = SETTINGS, groups, ITEMS
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_opt", "OPT_PREFIX": "PP OPT"}, store=self.store, api=self.api,
                               clock=Clock(), now=lambda: NOW)

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context(customer="Walk In"))
        return self.svc.answer("/opt/check", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_marks_with_its_own_key(self):
        self.assertEqual(self.check("check-a", self.A)[1]["verdict"], "refuse")       # A marks spectacle lenses
        self.assertEqual(self.check("check-b", self.B)[1]["verdict"], "allow")        # B does not
        seen = sorted({c[1:3] for c in self.api.calls})
        self.assertEqual(seen, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_another_shops_secret_is_refused(self):
        self.assertEqual(self.check("check-b", self.A)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.check("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.check("check-a", None)[0], 401)

    def test_a_shop_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.check("check-c", "shop-c.ivendnext.com")[0], 503)

    def test_the_marks_are_kept_per_shop(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)

    def test_a_new_key_reads_the_shop_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_opt:sub:check": "check-a", "user:opt@x": "key-a2:sec-a2"}})
        self.check("check-a", self.A)
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "settings"], ["key-a:sec-a", "key-a2:sec-a2"])
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "items"], ["key-a:sec-a", "key-a2:sec-a2"])


class ShopApi(unittest.TestCase):
    """``ShopApi`` against a stand-in shop on a local port: the key, the paths and filters, a missing settings record, an
    error, a cut answer, no redirect."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []

        class Shop(BaseHTTPRequestHandler):
            def do_GET(h):
                cls.seen.append((h.path, h.headers.get("Authorization")))
                path, _, q = h.path.partition("?")
                if "Redirect" in path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/Item%20Group?{q}")
                    h.end_headers()
                    return
                code, body = {
                    "/api/resource/PP%20OPT%20Settings/Default": (200, {"data": SETTINGS}),
                    "/api/resource/NONE%20Settings/Default": (404, {"exc_type": "DoesNotExistError"}),
                    "/api/resource/LOCKED%20Settings/Default": (403, {"exc_type": "PermissionError"}),
                    "/api/resource/CUT%20Settings/Default": (200, None),
                    "/api/resource/LIST%20Settings/Default": (200, {"data": []}),
                    "/api/resource/Item%20Group": (200, {"data": GROUPS}),
                    "/api/resource/Item": (200, {"data": ITEMS[:1]}),
                    "/api/resource/PP%20OPT%20Prescription": (200, {"data": [RX_SPECS]}),
                }[path]
                if body is None:                 # an answer cut short: more promised than sent
                    h.send_response(code)
                    h.send_header("Content-Length", "100")
                    h.end_headers()
                    h.wfile.write(b'{"da')
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

    def args(self):
        return dict(urllib.parse.parse_qsl(self.seen[-1][0].split("?", 1)[1]))

    def test_reads_the_settings_record_with_the_token_and_none_when_missing(self):
        self.assertEqual(self.api.settings(self.url, "k:s", "PP OPT"), SETTINGS)
        self.assertEqual(self.seen[-1][1], "token k:s")
        self.assertIsNone(self.api.settings(self.url, "k:s", "NONE"))

    def test_reads_every_item_group_with_the_apps_mark(self):
        self.assertEqual(self.api.groups(self.url, "k:s", "PP OPT"), GROUPS)
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), a["limit_page_length"]), (["name", "lft", "rgt", "pp_opt_needs"], "0"))

    def test_reads_the_named_items_mark(self):
        self.api.items(self.url, "k:s", "PP OPT", ["SV-LENS"])
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), json.loads(a["filters"]), a["limit_page_length"]),
                         (["name", "pp_opt_needs", "variant_of"], [["name", "in", ["SV-LENS"]]], "0"))

    def test_reads_only_two_fields_of_the_customers_prescriptions(self):
        self.assertEqual(self.api.prescriptions(self.url, "k:s", "PP OPT", "Ana Lopez"), [RX_SPECS])
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), json.loads(a["filters"]), a["limit_page_length"]),
                         (["kind", "valid_until"], [["customer", "=", "Ana Lopez"]], "0"))

    def test_a_refusal_or_an_answer_that_is_not_records_is_unreadable(self):
        for prefix in ("LOCKED", "LIST"):
            with self.assertRaises(app.ShopUnreadable):
                self.api.settings(self.url, "k:s", prefix)

    def test_a_cut_answer_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.settings(self.url, "k:s", "CUT")

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api._get(self.url, "k:s", "/api/resource/Redirect")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.groups("http://127.0.0.1:9", "k:s", "PP OPT")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": URL, "secrets": {
            "ivendnext_opt:sub:check": "check-a", "user:opt@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_opt", "OPT_PREFIX": "PP OPT"}, store=self.store, api=Api(),
                          now=lambda: NOW)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context(customer="Walk In"))
        for b64 in (False, True):
            out = self.entry(self.event("/opt/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual((out["statusCode"], json.loads(out["body"])["verdict"]), (200, "refuse"))
        out = self.entry(self.event("/opt/check", raw, signed(raw, "wrong", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed check, and one log line that carries no shop data."""

    def test_health_a_signed_check_and_a_clean_log(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE, api=Api(), now=lambda: NOW), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            raw = raw_of(context(customer="SECRET CUSTOMER"))
            req = urllib.request.Request(base + "/opt/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            bad = urllib.request.Request(base + "/opt/check", data=raw, headers=signed(raw, "x"), method="POST")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(e.exception.code, 401)
            e.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()
        text = log.getvalue()
        self.assertIn('"status": 200', text)
        self.assertNotIn("SECRET", text)
        self.assertNotIn(CHECK, text)


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(ONE)
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {p: (k, CHECK) for p, k in app.ROUTES.items()}
        self.assertEqual(set(self.routes), set(app.ROUTES))     # every signed point route of the service

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
