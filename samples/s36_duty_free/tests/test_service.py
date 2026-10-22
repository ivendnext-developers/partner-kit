"""S36's service over the wire: the call checked with the check's secret, the shop's settings and item groups read with
the app's key and kept a minute, the basket's items and the passenger's earlier sales read live, one shop or many (the app
template's handshake), and the down cases the till turns into its down answer.

    python3 -m unittest discover -s samples/s36_duty_free/tests -p 'test_*.py'
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
from test_rules import GROUPS, NOW, PASS, SETTINGS, bcbp, context, leg, line  # noqa: E402

CHECK = "check-secret-1"
URL = "https://shop.example"
ONE = {"IVN_CHECK_SECRET": CHECK, "IVN_SHOP_URL": URL, "IVN_SHOP_KEY": "k:s"}
ITEMS = [{"name": "WHISKY-1L", "stock_uom": "Nos", "pp_dfa_counts_as": 1},
         {"name": "VODKA-75", "stock_uom": "Nos", "pp_dfa_counts_as": 0.75},
         {"name": "CIG-CARTON", "stock_uom": "Nos", "pp_dfa_counts_as": 200},
         {"name": "GIN", "stock_uom": "Nos", "pp_dfa_counts_as": None},
         {"name": "BEER", "stock_uom": "Bottle", "pp_dfa_counts_as": 0.5}]


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
    """A stand-in for the shop's reads, keyed by the shop's address; records every call."""

    def __init__(self):
        self.settings_by = {URL: SETTINGS}
        self.groups_by = {URL: GROUPS}
        self.items_by = {URL: ITEMS}
        self.uoms_by = {"BEER": [{"uom": "Bottle", "conversion_factor": 1}, {"uom": "Case", "conversion_factor": 6}]}
        self.sales = {}                     # pass key -> [(name, [rows])]
        self.calls, self.down, self.refuse, self.refuse_sales = [], False, False, False

    def _gate(self, what=""):
        if self.refuse or (self.refuse_sales and what == "sales"):
            raise app.KeyRefused("403")
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

    def uoms(self, url, key, code):
        self.calls.append(("uoms", url, key, code))
        self._gate()
        return self.uoms_by.get(code, [])

    def earlier(self, url, key, attribute, pass_text):
        self.calls.append(("earlier", url, key, attribute, pass_text))
        self._gate("sales")
        return [n for n, _rows in self.sales.get(pass_text[:60], [])]

    def sale(self, url, key, name):
        self.calls.append(("sale", url, key, name))
        self._gate("sales")
        return next(rows for runs in self.sales.values() for n, rows in runs if n == name)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def row(code, group, qty):
    return {"item_code": code, "item_group": group, "stock_qty": qty}


class OneShop(unittest.TestCase):
    def setUp(self):
        self.api, self.clock = Api(), Clock()
        self.svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: NOW)

    def check(self, ctx, secret=CHECK, ts=None):
        raw = raw_of(ctx)
        return self.svc.answer("/dfa/check", signed(raw, secret, ts), raw)

    def verdict(self, ctx):
        return self.check(ctx)[1]

    def test_a_pass_from_here_today_within_the_allowance_is_allowed(self):
        self.assertEqual(self.check(context([line("WHISKY-1L", "Whisky", 2)])), (200, {"verdict": "allow"}))

    def test_no_pass_is_refused_without_reading_the_shop(self):
        self.assertEqual(self.verdict(context(pass_text="")), {"verdict": "refuse", "reason": app.dutyfree.NO_PASS})
        self.assertEqual(self.api.calls, [])

    def test_a_pass_from_elsewhere_or_another_day_is_refused(self):
        self.assertIn("from LHR", self.verdict(context(pass_text=bcbp(leg("LHR", "DXB"))))["reason"])
        self.assertEqual(self.verdict(context(pass_text=bcbp(leg(day=200))))["reason"], app.dutyfree.OTHER_DAY)

    def test_the_airports_day_comes_from_the_settings(self):
        late = NOW + 9.5 * 3600                     # 21:30 UTC: already the 23rd in Dubai (UTC+4)
        svc = app.Service(ONE, api=self.api, clock=self.clock, now=lambda: late)
        raw = raw_of(context(pass_text=bcbp(leg(day=295))))
        self.assertEqual(svc.answer("/dfa/check", signed(raw, CHECK), raw)[1]["reason"], app.dutyfree.OTHER_DAY)
        raw = raw_of(context(pass_text=bcbp(leg(day=297))))
        self.assertEqual(svc.answer("/dfa/check", signed(raw, CHECK), raw)[1], {"verdict": "allow"})

    def test_past_the_allowance_is_refused_counting_each_items_measure(self):
        out = self.verdict(context([line("WHISKY-1L", "Whisky", 2), line("VODKA-75", "Spirits", 3)]))
        self.assertEqual(out["reason"], "Spirits: 4.25 litres on this boarding pass; the allowance is 4. Take some off the sale.")
        self.assertEqual(self.verdict(context([line("CIG-CARTON", "Tobacco", 2)])), {"verdict": "allow"})
        self.assertIn("Tobacco: 600 cigarettes", self.verdict(context([line("CIG-CARTON", "Tobacco", 3)]))["reason"])

    def test_an_item_with_no_measure_counts_one_per_unit(self):
        self.assertEqual(self.verdict(context([line("GIN", "Spirits", 4)])), {"verdict": "allow"})
        self.assertIn("Spirits: 5 litres", self.verdict(context([line("GIN", "Spirits", 5)]))["reason"])

    def test_a_line_in_another_unit_counts_its_stock_units(self):
        self.api.groups_by[URL] = GROUPS + [{"name": "Beer", "lft": 13, "rgt": 14, "pp_dfa_allowance": 4, "pp_dfa_unit": "litres"}]
        self.assertIn("Beer: 6 litres", self.verdict(context([line("BEER", "Beer", 2, uom="Case")]))["reason"])
        self.assertEqual(self.verdict(context([line("BEER", "Beer", 8, uom="Bottle")])), {"verdict": "allow"})
        self.assertEqual([c[3] for c in self.api.calls if c[0] == "uoms"], ["BEER"])     # read only for the other unit

    def test_the_passengers_earlier_sales_on_the_same_pass_count(self):
        self.api.sales = {PASS[:60]: [("POS-1", [row("WHISKY-1L", "Whisky", 3)]), ("POS-2", [row("BREAD", "Food", 9)])]}
        self.assertEqual(self.verdict(context([line("WHISKY-1L", "Whisky", 1)])), {"verdict": "allow"})
        self.assertIn("Spirits: 5 litres", self.verdict(context([line("WHISKY-1L", "Whisky", 2)]))["reason"])
        found = [c for c in self.api.calls if c[0] == "earlier"][0]
        self.assertEqual((found[3], found[4]), ("PP DFA Boarding Pass", PASS))

    def test_an_earlier_return_takes_its_amount_back_and_an_earlier_items_measure_is_read(self):
        self.api.sales = {PASS[:60]: [("POS-1", [row("VODKA-75", "Spirits", 4)]), ("POS-2", [row("VODKA-75", "Spirits", -4)])]}
        self.assertEqual(self.verdict(context([line("WHISKY-1L", "Whisky", 4)])), {"verdict": "allow"})
        self.assertIn(("items", URL, "k:s", ("VODKA-75",)), self.api.calls)

    def test_earlier_sales_are_not_read_when_the_shop_says_so(self):
        self.api.settings_by[URL] = dict(SETTINGS, count_earlier_sales=0)
        self.api.sales = {PASS[:60]: [("POS-1", [row("WHISKY-1L", "Whisky", 4)])]}
        self.assertEqual(self.verdict(context([line("WHISKY-1L", "Whisky", 1)])), {"verdict": "allow"})
        self.assertFalse([c for c in self.api.calls if c[0] in ("earlier", "sale")])

    def test_a_sale_with_no_limited_item_reads_no_items_and_no_earlier_sales(self):
        self.api.sales = {PASS[:60]: [("POS-1", [row("WHISKY-1L", "Whisky", 9)])]}
        self.assertEqual(self.verdict(context([line("BREAD", "Food", 3)])), {"verdict": "allow"})
        self.assertEqual(sorted({c[0] for c in self.api.calls}), ["groups", "settings"])

    def test_a_refund_is_allowed_without_reading_anything(self):
        self.assertEqual(self.verdict(context([line("WHISKY-1L", "Whisky", -9)], pass_text="", stage="return")),
                         {"verdict": "allow"})
        self.assertEqual(self.api.calls, [])

    def test_an_exchange_is_judged_for_what_it_sells(self):
        ctx = context([line("WHISKY-1L", "Whisky", -1), line("WHISKY-1L", "Whisky", 5)], stage="return")
        self.assertEqual(self.verdict(ctx), {"verdict": "allow"})                          # 5 sold, 1 back: 4
        ctx["lines"][1]["qty_milli"] = 6000
        self.assertIn("Spirits: 5 litres", self.verdict(ctx)["reason"])

    def test_an_item_on_the_sale_the_shop_does_not_return_is_a_503(self):
        self.assertEqual(self.check(context([line("NEW-RUM", "Spirits", 1)]))[0], 503)

    def test_the_check_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(context())
        h = signed(raw, CHECK)
        self.assertEqual(self.svc.answer("/dfa/check", h, raw.replace(b"WHISKY", b"WHISKE"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(self.svc.answer("/dfa/check", signed(raw, CHECK), raw)[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/cpn/check", signed(raw, CHECK), raw)[0], 404)

    def test_the_settings_and_groups_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.clock.t += 59
        self.check(context())
        self.assertEqual([c for c in self.api.calls if c[0] in ("settings", "groups")],
                         [("settings", URL, "k:s", "PP DFA"), ("groups", URL, "k:s", "PP DFA")])
        self.clock.t += 2
        self.check(context())
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)

    def test_items_and_earlier_sales_are_never_kept(self):
        self.check(context())
        self.api.sales = {PASS[:60]: [("POS-1", [row("WHISKY-1L", "Whisky", 4)])]}
        self.assertEqual(self.verdict(context())["verdict"], "refuse")

    def test_no_settings_record_is_any_airport(self):
        self.api.settings_by[URL] = None
        self.assertEqual(self.verdict(context(pass_text=bcbp(leg("LHR", "JFK", day=295)))), {"verdict": "allow"})

    def test_the_shop_down_is_a_503_so_the_down_answer_applies(self):
        self.api.down = True
        self.assertEqual(self.check(context())[0], 503)

    def test_the_earlier_sales_down_is_a_503_never_an_allow(self):
        self.check(context())                                   # the settings are kept
        self.api.down = True
        self.assertEqual(self.check(context())[0], 503)

    def test_a_refused_key_refuses_the_sale_in_words(self):
        self.api.refuse = True
        self.assertEqual(self.check(context()), (200, {"verdict": "refuse", "reason": app.KEY_REFUSED}))
        self.assertTrue(len(app.KEY_REFUSED) <= 140)

    def test_the_sales_read_alone_refused_refuses_a_limited_sale_only(self):
        self.api.refuse_sales = True
        self.assertEqual(self.check(context()), (200, {"verdict": "refuse", "reason": app.KEY_REFUSED}))
        self.assertEqual(self.verdict(context([line("BREAD", "Food", 1)])), {"verdict": "allow"})

    def test_groups_that_are_not_records_are_a_503(self):
        self.api.groups_by[URL] = None
        self.assertEqual(self.check(context())[0], 503)

    def test_the_prefix_names_the_sale_detail_and_the_records(self):
        self.api.groups_by[URL] = [{k.replace("pp_dfa_", "ivendnext_dfa_"): v for k, v in g.items()} for g in GROUPS]
        self.api.items_by[URL] = [{k.replace("pp_dfa_", "ivendnext_dfa_"): v for k, v in i.items()} for i in ITEMS]
        svc = app.Service(dict(ONE, DFA_PREFIX="IVENDNEXT DFA"), api=self.api, clock=self.clock, now=lambda: NOW)
        raw = raw_of(context(prefix="IVENDNEXT DFA"))
        svc.answer("/dfa/check", signed(raw, CHECK), raw)
        self.assertEqual(self.api.calls[0][3], "IVENDNEXT DFA")
        self.assertIn("IVENDNEXT DFA Boarding Pass", [c[3] for c in self.api.calls if c[0] == "earlier"])
        raw = raw_of(context(prefix="PP DFA"))                       # another app's sale detail is not this app's pass
        self.assertEqual(svc.answer("/dfa/check", signed(raw, CHECK), raw)[1]["reason"], app.dutyfree.NO_PASS)


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_dfa:sub:allowance": f"check-{n}", "user:dfa@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_dfa:sub:allowance": "check-c"}})     # no user key
        self.api = Api()
        for site, airports in ((self.A, "DXB"), (self.B, "LHR")):
            u = f"https://{site}"
            self.api.settings_by[u], self.api.groups_by[u], self.api.items_by[u] = dict(SETTINGS, airports=airports), GROUPS, ITEMS
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_dfa"}, store=self.store, api=self.api, clock=Clock(),
                               now=lambda: NOW)

    def check(self, secret, site, ctx=None):
        raw = raw_of(ctx or context())
        return self.svc.answer("/dfa/check", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_settings_with_its_own_key(self):
        self.assertEqual(self.check("check-a", self.A)[1]["verdict"], "allow")         # A: Dubai, the pass leaves DXB
        self.assertEqual(self.check("check-b", self.B)[1]["verdict"], "refuse")        # B: London
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

    def test_the_settings_are_kept_per_shop(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "settings"]), 2)

    def test_a_new_key_reads_the_settings_again(self):
        self.check("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_dfa:sub:allowance": "check-a", "user:dfa@x": "key-a2:sec-a2"}})
        self.check("check-a", self.A)
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "settings"], ["key-a:sec-a", "key-a2:sec-a2"])


class ShopApi(unittest.TestCase):
    """``ShopApi`` against a stand-in shop on a local port: the key, the paths and filters, a missing settings record, a
    refusal, an error, a cut answer, no redirect."""

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
                    "/api/resource/PP%20DFA%20Settings/Default": (200, {"data": SETTINGS}),
                    "/api/resource/NONE%20Settings/Default": (404, {"exc_type": "DoesNotExistError"}),
                    "/api/resource/LOCKED%20Settings/Default": (403, {"exc_type": "PermissionError"}),
                    "/api/resource/BROKEN%20Settings/Default": (500, {"exc_type": "x"}),
                    "/api/resource/CUT%20Settings/Default": (200, None),
                    "/api/resource/Item%20Group": (200, {"data": GROUPS}),
                    "/api/resource/Item": (200, {"data": ITEMS[:1]}),
                    "/api/resource/Item/BEER%2FCASE": (200, {"data": {"name": "BEER/CASE", "uoms": [{"uom": "Case", "conversion_factor": 6}]}}),
                    "/api/resource/POS%20Invoice": (200, {"data": [{"name": "POS-1"}, {"name": 7}]}),
                    "/api/resource/POS%20Invoice/POS-1": (200, {"data": {"name": "POS-1", "items": [row("WHISKY-1L", "Whisky", 2)]}}),
                    "/api/resource/POS%20Invoice/LIST": (200, {"data": []}),
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
        self.assertEqual(self.api.settings(self.url, "k:s", "PP DFA"), SETTINGS)
        self.assertEqual(self.seen[-1][1], "token k:s")
        self.assertIsNone(self.api.settings(self.url, "k:s", "NONE"))

    def test_reads_every_item_group_with_the_apps_two_fields(self):
        self.assertEqual(self.api.groups(self.url, "k:s", "PP DFA"), GROUPS)
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), a["limit_page_length"]),
                         (["name", "lft", "rgt", "pp_dfa_allowance", "pp_dfa_unit"], "0"))

    def test_reads_the_named_items_measure(self):
        self.api.items(self.url, "k:s", "PP DFA", ["WHISKY-1L"])
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), json.loads(a["filters"])),
                         (["name", "stock_uom", "pp_dfa_counts_as"], [["name", "in", ["WHISKY-1L"]]]))

    def test_reads_an_items_units_by_its_encoded_name(self):
        self.assertEqual(self.api.uoms(self.url, "k:s", "BEER/CASE"), [{"uom": "Case", "conversion_factor": 6}])

    def test_finds_earlier_sales_by_the_passs_first_60_characters_matched_as_written(self):
        text = PASS[:30] + "%_" + PASS[32:]
        self.assertEqual(self.api.earlier(self.url, "k:s", "PP DFA Boarding Pass", text), ["POS-1"])   # a name that is not text is dropped
        a = self.args()
        f = json.loads(a["filters"])
        self.assertEqual(f[0], ["POS Invoice Sale Attribute", "sale_attribute", "=", "PP DFA Boarding Pass"])
        self.assertEqual(f[1][:3], ["POS Invoice Sale Attribute", "attribute_value", "like"])
        self.assertEqual(f[1][3], text[:30] + "\\%\\_" + text[32:60] + "%")
        self.assertEqual((f[2], a["limit_page_length"]), (["docstatus", "=", 1], str(app.EARLIER_MAX)))

    def test_reads_an_earlier_sales_lines(self):
        self.assertEqual(self.api.sale(self.url, "k:s", "POS-1"), [row("WHISKY-1L", "Whisky", 2)])

    def test_a_refusal_is_key_refused_and_an_error_is_unreadable(self):
        with self.assertRaises(app.KeyRefused):
            self.api.settings(self.url, "k:s", "LOCKED")
        with self.assertRaises(app.ShopUnreadable) as e:
            self.api.settings(self.url, "k:s", "BROKEN")
        self.assertNotIsInstance(e.exception, app.KeyRefused)

    def test_a_cut_answer_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.settings(self.url, "k:s", "CUT")

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api._get(self.url, "k:s", "/api/resource/Redirect")

    def test_an_answer_that_is_not_records_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.sale(self.url, "k:s", "LIST")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            self.api.groups("http://127.0.0.1:9", "k:s", "PP DFA")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": URL,
                                                "secrets": {"ivendnext_dfa:sub:allowance": "check-a", "user:dfa@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_dfa"}, store=self.store, api=Api(), now=lambda: NOW)
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context(pass_text=""))
        for b64 in (False, True):
            out = self.entry(self.event("/dfa/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual((out["statusCode"], json.loads(out["body"])["verdict"]), (200, "refuse"))
        out = self.entry(self.event("/dfa/check", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
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
            raw = raw_of(context([line("WHISKY-1L", "Whisky", 9)], pass_text=bcbp(name="SECRET/PASSENGER")))
            req = urllib.request.Request(base + "/dfa/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            bad = urllib.request.Request(base + "/dfa/check", data=raw, headers=signed(raw, "x"), method="POST")
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


if __name__ == "__main__":
    unittest.main()
