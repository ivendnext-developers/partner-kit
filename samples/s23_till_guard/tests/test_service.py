"""S23's service over the wire: each route checked with its own secret, the shop's settings read with the app's key and
kept a minute, one shop or many (the app template's handshake), and the down cases the till turns into its down answer.

    python3 -m unittest discover -s samples/s23_till_guard/tests -p 'test_*.py'
"""

import base64
import hashlib
import hmac
import io
import json
import os
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
from test_guard import SETTINGS, context, line, scan  # noqa: E402

CHECK, SCAN = "check-secret-1", "scan-secret-1"
ONE = {"IVN_CHECK_SECRET": CHECK, "IVN_SCAN_SECRET": SCAN, "IVN_SHOP_URL": "https://shop.example", "IVN_SHOP_KEY": "k:s"}


def raw_of(point, ctx):
    return json.dumps({"point": point, "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "Content-Type": "application/json"}
    if site:
        h[shops.SITE_HEADER] = site
    return h


class Reader:
    """A stand-in for the shop's record API: answers from a dict, counts its reads, can be switched off."""

    def __init__(self, by_url=None):
        self.by_url, self.calls, self.down = by_url or {"https://shop.example": SETTINGS}, [], False

    def __call__(self, url, key, prefix):
        self.calls.append((url, key, prefix))
        if self.down:
            raise app.ShopUnreadable("down")
        return self.by_url.get(url)


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def call(svc, path, raw, headers):
    return svc.answer(path, headers, raw)


class OneShop(unittest.TestCase):
    def setUp(self):
        self.reader, self.clock = Reader(), Clock()
        self.svc = app.Service(ONE, reader=self.reader, clock=self.clock)

    def check(self, ctx, secret=CHECK, ts=None):
        raw = raw_of("check/1", ctx)
        return call(self.svc, "/tgr/check", raw, signed(raw, secret, ts))

    def scan(self, ctx, secret=SCAN):
        raw = raw_of("capture/1", ctx)
        return call(self.svc, "/tgr/scan", raw, signed(raw, secret))

    def test_the_check_answers_from_the_shops_rules(self):
        self.assertEqual(self.check(context()), (200, {"verdict": "allow"}))
        code, out = self.check(context([line(1, "PEN-01", rate=1)]))
        self.assertEqual((code, out["verdict"]), (200, "refuse"))

    def test_the_scan_beeps_and_asks(self):
        self.assertEqual(self.scan(scan()), (200, {"verdict": "confirm",
                                                   "question": "PEN-01: Check this item before it goes on the sale. Add it?"}))

    def shelf_service(self, slow=0.0, down=False):
        """A shop with the shelf-life warning on: two batches of MILK-1 in Main - S, the reads counted. ``slow`` moves the
        clock that far forward during the batch read (a shop slow to answer); ``down`` makes the read fail."""
        self.reader.by_url = {"https://shop.example": dict(SETTINGS, warn_shorter_shelf_life=1)}
        self.reads = []

        def batches(url, key, item, store, timeout):
            self.reads.append(("batches", item, store, round(timeout, 3)))
            self.clock.t += slow
            if down:
                raise app.ShopUnreadable("down")
            return [("B-LATE", 4.0), ("B-SOON", 2.0), ("B-EMPTY", 0.0)]

        def expiry(url, key, batch, timeout):
            self.reads.append(("expiry", batch))
            return {"B-LATE": "2026-12-01", "B-SOON": "2026-11-02"}[batch]

        self.svc = app.Service(ONE, reader=self.reader, clock=self.clock, batches=batches, expiry=expiry)

    def test_the_shelf_warning_is_a_notice_and_the_expiry_dates_are_kept(self):
        self.shelf_service()
        ctx = scan("MILK-1")
        self.assertEqual(self.scan(ctx), (200, {"verdict": "notice",
                                               "message": "MILK-1: sell batch B-SOON first. It expires 2026-11-02."}))
        self.assertEqual(self.reads, [("batches", "MILK-1", "Main - S", 1.0), ("expiry", "B-LATE"), ("expiry", "B-SOON")])
        self.scan(ctx)                                  # a warm scan reads the batches again, never an expiry date
        self.assertEqual(self.reads[3:], [("batches", "MILK-1", "Main - S", 1.0)])

    def test_a_shelf_answer_that_would_come_after_one_second_is_a_plain_allow(self):
        self.shelf_service(slow=1.2)
        self.assertEqual(self.scan(scan("MILK-1")), (200, {"verdict": "allow"}))

    def test_a_shop_that_cannot_be_read_lets_the_item_on_with_nothing_shown(self):
        self.shelf_service(down=True)
        self.assertEqual(self.scan(scan("MILK-1")), (200, {"verdict": "allow"}))

    def test_a_shop_answer_of_the_wrong_shape_is_a_plain_allow_never_a_server_error(self):
        self.shelf_service()
        for bad in (TypeError("no shop"), ValueError("not a number"), OSError("reset")):
            def batches(url, key, item, store, timeout, bad=bad):
                raise bad
            self.svc.batches = batches
            self.assertEqual(self.scan(scan("MILK-1")), (200, {"verdict": "allow"}))

    def test_with_the_warning_off_the_scan_still_asks(self):
        self.shelf_service()
        self.reader.by_url = {"https://shop.example": SETTINGS}
        self.assertEqual(self.scan(scan())[1]["verdict"], "confirm")
        self.assertEqual(self.reads, [])

    def test_each_route_takes_only_its_own_secret(self):
        self.assertEqual(self.check(context(), secret=SCAN)[0], 401)
        self.assertEqual(self.scan(scan(), secret=CHECK)[0], 401)
        self.assertEqual(self.check(context(), secret="wrong")[0], 401)

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.check(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of("check/1", context())
        h = signed(raw, CHECK)
        self.assertEqual(call(self.svc, "/tgr/check", raw.replace(b"1250", b"1251"), h)[0], 401)

    def test_a_body_it_cannot_read_is_a_400(self):
        raw = b'{"point":"check/1","context":{}}'
        self.assertEqual(call(self.svc, "/tgr/check", raw, signed(raw, CHECK))[0], 400)

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of("check/1", context())
        self.assertEqual(call(self.svc, "/tgr/other", raw, signed(raw, CHECK))[0], 404)

    def test_the_settings_are_read_with_the_apps_key_and_kept_a_minute(self):
        self.check(context())
        self.scan(scan())
        self.assertEqual(self.reader.calls, [("https://shop.example", "k:s", "PP TGR")])
        self.clock.t += app.SETTINGS_TTL + 1
        self.check(context())
        self.assertEqual(len(self.reader.calls), 2)

    def test_a_changed_setting_is_used_after_the_minute(self):
        self.check(context())
        self.reader.by_url["https://shop.example"] = dict(SETTINGS, approval_from=1)
        self.assertEqual(self.check(context())[1]["verdict"], "allow")          # still the minute's rules
        self.clock.t += app.SETTINGS_TTL + 1
        self.assertEqual(self.check(context())[1]["verdict"], "approve")

    def test_no_settings_record_yet_allows_everything(self):
        self.reader.by_url = {}
        self.assertEqual(self.check(context([line(1, "PEN-01", qty=900, rate=1)])), (200, {"verdict": "allow"}))

    def test_the_shop_down_with_nothing_read_is_a_503_so_the_down_answer_applies(self):
        self.reader.down = True
        self.assertEqual(self.check(context())[0], 503)
        self.assertEqual(self.scan(scan())[0], 503)

    def test_the_shop_down_uses_the_last_rules_for_ten_minutes_then_503(self):
        self.check(context())
        self.reader.down = True
        self.clock.t += app.SETTINGS_TTL + 1
        self.assertEqual(self.check(context([line(1, "PEN-01", rate=1)]))[1]["verdict"], "refuse")
        self.clock.t += app.SETTINGS_STALE
        self.assertEqual(self.check(context())[0], 503)

    def test_a_return_is_allowed_without_reading_the_shop(self):
        self.reader.down = True
        self.assertEqual(self.check(context([line(1, "PEN-01", qty=-1, rate=1)], stage="return")), (200, {"verdict": "allow"}))
        self.assertEqual(self.reader.calls, [])

    def test_a_sale_with_no_sold_line_still_reads_the_shop(self):
        self.assertEqual(self.check(context([], grand=900000))[1]["verdict"], "approve")

    def test_an_exchange_reads_the_shop_and_judges_what_it_sells(self):
        out = self.check(context([line(1, "TV", qty=-1), line(2, "PEN-01", rate=1)], stage="return"))
        self.assertEqual((out[0], out[1]["verdict"]), (200, "refuse"))
        self.assertEqual(len(self.reader.calls), 1)

    def test_the_prefix_names_the_settings_record_type(self):
        svc = app.Service(dict(ONE, TGR_PREFIX="IVENDNEXT TGR"), reader=self.reader, clock=self.clock)
        raw = raw_of("check/1", context())
        call(svc, "/tgr/check", raw, signed(raw, CHECK))
        self.assertEqual(self.reader.calls[-1][2], "IVENDNEXT TGR")


class LowestPrices(unittest.TestCase):
    """1.3.0's *Lowest prices*: one read of the list's rows for the basket's priced items, kept a minute, standing in for
    ten while the shop is down, then 503 (the till's down answer); no read when the list is blank or nothing is priced."""
    ROWS = [{"item_code": "BREAD", "uom": "Nos", "price_list_rate": 10, "currency": "AED"},
            {"item_code": "MILK", "uom": "Nos", "price_list_rate": 3, "currency": "AED"}]

    def setUp(self):
        self.reader, self.clock, self.reads, self.down = Reader(), Clock(), [], False
        self.reader.by_url = {"https://shop.example": dict(SETTINGS, approval_from=0, lowest_price_list="Lowest")}

        def prices(url, key, plist, items, currency, timeout):
            self.reads.append((url, key, plist, list(items)))
            if self.down:
                raise app.ShopUnreadable("down")
            return [r for r in self.ROWS if r["item_code"] in items]

        self.svc = app.Service(ONE, reader=self.reader, clock=self.clock, prices=prices, today=lambda: "2026-10-28")

    def check(self, ctx):
        raw = raw_of("check/1", ctx)
        return call(self.svc, "/tgr/check", raw, signed(raw, CHECK))

    def test_a_line_below_its_lowest_price_calls_a_manager_with_one_read(self):
        code, out = self.check(context([line(1, rate=999), line(2, "MILK", rate=300), line(3, "MILK", rate=0)]))
        self.assertEqual((code, out["verdict"]), (200, "approve"))
        self.assertEqual(self.reads, [("https://shop.example", "k:s", "Lowest", ["BREAD", "MILK"])])

    def test_the_prices_are_kept_a_minute_and_a_new_item_is_read_alone(self):
        self.check(context([line(1, rate=1000)]))
        self.clock.t += 59
        self.check(context([line(1, rate=1000), line(2, "MILK", rate=300)]))
        self.assertEqual([r[3] for r in self.reads], [["BREAD"], ["MILK"]])
        self.clock.t += 2
        self.check(context([line(1, rate=1000)]))
        self.assertEqual([r[3] for r in self.reads], [["BREAD"], ["MILK"], ["BREAD"]])

    def test_the_shop_down_uses_the_last_prices_for_ten_minutes_then_503(self):
        self.assertEqual(self.check(context([line(1, rate=999)]))[1]["verdict"], "approve")
        self.down, self.clock.t = True, self.clock.t + 61
        self.reader.down = False
        self.assertEqual(self.check(context([line(1, rate=999)]))[1]["verdict"], "approve")
        self.clock.t += 600
        self.assertEqual(self.check(context([line(1, rate=999)]))[0], 503)

    def test_no_read_when_the_list_is_blank_or_nothing_is_priced(self):
        self.check(context([line(1, rate=0)]))
        self.reader.by_url = {"https://shop.example": dict(SETTINGS, approval_from=0)}
        self.clock.t += 61
        self.assertEqual(self.check(context([line(1, rate=999)])), (200, {"verdict": "allow"}))
        self.assertEqual(self.reads, [])

    def test_a_refusal_is_answered_before_any_price_is_read_and_survives_a_failed_read(self):
        self.reader.by_url = {"https://shop.example": dict(SETTINGS, approval_from=0, max_lines_per_sale=1,
                                                         lowest_price_list="Lowest")}
        self.down = True                                    # the right missing: every price read fails
        code, out = self.check(context([line(1), line(2)]))
        self.assertEqual((code, out["verdict"]), (200, "refuse"))
        code, out = self.check(context([line(1, rate=1)]))      # the placeholder price, one line
        self.assertEqual((code, out["verdict"]), (200, "refuse"))
        self.assertEqual(self.reads, [])
        self.assertEqual(self.check(context([line(1, rate=999)]))[0], 503)    # nothing refused: the read is owed

    def test_a_large_basket_is_read_in_chunks_that_keep_the_request_line_short(self):
        codes = ["محصول-" * 6 + f"{n:03}" for n in range(1, 61)]   # long Arabic codes: about 300 bytes each in a query string
        self.assertEqual(self.check(context([line(n, c, rate=500) for n, c in enumerate(codes, 1)]))[1]["verdict"], "allow")
        sizes = [sum(len(urllib.parse.quote(json.dumps(c))) + 3 for c in r[3]) for r in self.reads]
        self.assertGreater(len(self.reads), 1)
        self.assertTrue(all(n <= app.PRICE_CHUNK for n in sizes), sizes)
        self.assertEqual(sorted(c for r in self.reads for c in r[3]), sorted(codes))

    def test_a_slow_shop_runs_out_of_the_budget_answers_503_and_keeps_what_it_read(self):
        def slow(url, key, plist, items, currency, timeout):
            self.clock.t += 1.0                              # each read takes a second of the check's 2
            self.reads.append(list(items))
            return []
        self.svc.prices = slow
        codes = ["X" * 120 + f"{n:03}" for n in range(1, 61)]
        basket = context([line(n, c, rate=500) for n, c in enumerate(codes, 1)])
        self.assertEqual(self.check(basket)[0], 503)
        first = [c for r in self.reads for c in r]
        self.reads.clear()
        self.check(basket)                                   # the next press reads only what the first did not
        self.assertFalse(set(first) & {c for r in self.reads for c in r})

    def test_each_price_read_is_given_only_the_check_s_time_left(self):
        given = []

        def timed(url, key, plist, items, currency, timeout):
            given.append((round(self.clock.t - start, 3), timeout))
            self.clock.t += 0.7
            return []
        self.svc.prices, start = timed, self.clock.t
        self.check(context([line(n, "X" * 120 + f"{n:03}", rate=500) for n in range(1, 61)]))
        self.assertGreater(len(given), 2)
        self.assertTrue(all(t <= min(app.READ_TIMEOUT, app.CHECK_BUDGET - at) + 1e-9 for at, t in given), given)

    def test_a_slow_settings_read_counts_against_the_check_s_time(self):
        def slow_settings(url, key, prefix):
            self.clock.t += 1.9                              # the settings took 1.9 s: too little is left to read prices
            return dict(SETTINGS, approval_from=0, lowest_price_list="Lowest")
        self.svc.reader = slow_settings
        self.assertEqual(self.check(context([line(1, rate=999)]))[0], 503)
        self.assertEqual(self.reads, [])

    def test_a_large_sale_still_calls_a_manager_when_the_prices_cannot_be_read(self):
        self.reader.by_url = {"https://shop.example": dict(SETTINGS, approval_from=250, lowest_price_list="Lowest")}
        self.down = True
        code, out = self.check(context([line(1, rate=30000)]))
        self.assertEqual((code, out), (200, {"verdict": "approve", "reason": "The sale is 250.00 AED or more. Its lowest prices "
                                                                      "could not be checked. It needs a manager's approval."}))
        self.reader.by_url["https://shop.example"]["approval_answer"] = "ask"
        self.clock.t += 61
        code, out = self.check(context([line(1, rate=30000)]))
        self.assertEqual((code, out), (200, {"verdict": "ask", "question": "The sale is 250.00 AED or more. Its lowest prices could "
                                                                     "not be checked. Has a manager agreed to it?"}))

    def test_a_shop_whose_key_is_gone_is_a_503_never_a_crash(self):
        self.check(context([line(1, rate=1000)]))           # rules and prices read once
        self.clock.t += 61                                   # the prices are due again, the rules stand in from the cache
        self.svc.shop = None                                 # the shop's key gone (as a connect without its user key)
        self.assertEqual(self.check(context([line(1, "MILK", rate=300)]))[0], 503)   # an item never read: nothing to stand in


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_tgr:sub:guard": f"check-{n}", "ivendnext_tgr:sub:on_scan": f"scan-{n}", "user:tgr@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_tgr:sub:guard": "check-c"}})     # no user key
        self.reader = Reader({f"https://{self.A}": dict(SETTINGS, approval_from=10), f"https://{self.B}": SETTINGS})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_tgr", "TGR_PREFIX": "IVENDNEXT TGR"}, store=self.store,
                               reader=self.reader, clock=Clock())

    def check(self, secret, site, ctx=None):
        raw = raw_of("check/1", ctx or context())
        return call(self.svc, "/tgr/check", raw, signed(raw, secret, site=site))

    def test_each_shop_is_answered_from_its_own_rules_with_its_own_key(self):
        self.assertEqual(self.check("check-a", self.A)[1]["verdict"], "approve")        # A: approval from 10.00
        self.assertEqual(self.check("check-b", self.B)[1]["verdict"], "allow")          # B: approval from 5,000.00
        self.assertEqual(sorted(c[:2] for c in self.reader.calls),
                         [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_each_shops_lowest_prices_are_its_own(self):
        """Two retailers name a list the same: each one's rows are read with its own key and kept for it alone."""
        price = {f"https://{self.A}": 10, f"https://{self.B}": 5}
        reads = []

        def prices(url, key, plist, items, currency, timeout):
            reads.append((url, key))
            return [{"item_code": "BREAD", "uom": "Nos", "price_list_rate": price[url], "currency": "AED"}]

        self.reader.by_url = {u: dict(SETTINGS, approval_from=0, lowest_price_list="Lowest") for u in price}
        self.svc.prices = prices
        ctx = context([line(1, rate=700)])
        self.assertEqual(self.check("check-a", self.A, ctx)[1]["verdict"], "approve")    # A: lowest 10.00
        self.assertEqual(self.check("check-b", self.B, ctx)[1]["verdict"], "allow")      # B: lowest 5.00
        self.assertEqual(reads, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_another_shops_secret_is_refused(self):
        self.assertEqual(self.check("check-b", self.A)[0], 401)
        self.assertEqual(self.check("check-a", self.B)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.check("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.check("check-a", None)[0], 401)

    def test_the_scan_route_takes_the_scan_secret_only(self):
        raw = raw_of("capture/1", scan())
        self.assertEqual(call(self.svc, "/tgr/scan", raw, signed(raw, "check-a", site=self.A))[0], 401)
        self.assertEqual(call(self.svc, "/tgr/scan", raw, signed(raw, "scan-a", site=self.A))[0], 200)

    def test_a_shop_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.check("check-c", "shop-c.ivendnext.com")[0], 503)

    def test_the_cache_is_per_shop(self):
        self.check("check-a", self.A)
        self.check("check-b", self.B)
        self.check("check-a", self.A)
        self.assertEqual(len(self.reader.calls), 2)


class ShopApi(unittest.TestCase):
    """``read_settings`` against a stand-in shop on a local port: the key, the path, 404, an error, no redirect."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []

        class Shop(BaseHTTPRequestHandler):
            def do_GET(h):
                cls.seen.append((h.path, h.headers.get("Authorization")))
                if "Redirect" in h.path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20TGR%20Settings/Default")
                    h.end_headers()
                    return
                code, body = {"PP%20TGR%20Settings": (200, {"data": SETTINGS}),
                              # the shop's real 404 bodies (read on a test shop, 2026-10-13): a missing record names
                              # "<record type> <name>"; a missing record type names "DocType <record type>"
                              "None%20Settings": (404, {"exc_type": "DoesNotExistError", "_server_messages": json.dumps(
                                  [json.dumps({"message": "None Settings Default not found", "indicator": "red"})])}),
                              "Gone%20Settings": (404, {"exc_type": "DoesNotExistError", "_server_messages": json.dumps(
                                  [json.dumps({"message": "DocType Gone Settings not found", "indicator": "red"})])}),
                              "Broken%20Settings": (500, {"exc_type": "x"})}[h.path.split("/")[3]]
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

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_reads_the_default_record_with_the_token(self):
        self.assertEqual(app.read_settings(self.url, "k:s", "PP TGR"), SETTINGS)
        self.assertEqual(self.seen[-1], ("/api/resource/PP%20TGR%20Settings/Default", "token k:s"))

    def test_no_record_is_none_and_an_error_is_unreadable(self):
        self.assertIsNone(app.read_settings(self.url, "k:s", "None"))
        with self.assertRaises(app.ShopUnreadable):
            app.read_settings(self.url, "k:s", "Broken")

    def test_a_404_that_does_not_name_the_record_is_unreadable_never_rules_off(self):
        # a wrong prefix (no such record type) or a wrong address must not switch every rule off unflagged
        with self.assertRaises(app.ShopUnreadable):
            app.read_settings(self.url, "k:s", "Gone")

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            app.read_settings(self.url, "k:s", "Redirect")

    def test_nothing_listening_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):
            app.read_settings("http://127.0.0.1:9", "k:s", "PP TGR", timeout=0.5)


class PriceApi(unittest.TestCase):
    """``read_lowest`` against a stand-in shop: the record API's Item Price list, its filters and fields, an error."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []

        class Shop(BaseHTTPRequestHandler):
            def do_GET(h):
                cls.seen.append((h.path, h.headers.get("Authorization")))
                q = urllib.parse.parse_qs(urllib.parse.urlsplit(h.path).query)
                plist = json.loads(q["filters"][0])[0][2]
                code, body = {"Lowest": (200, {"data": [{"item_code": "BREAD", "price_list_rate": 10}]}),
                              "Odd": (200, {"data": {"not": "a list"}}), "Shut": (403, {"exc_type": "PermissionError"})}[plist]
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

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def test_reads_the_lists_rows_for_the_items_with_the_token(self):
        self.assertEqual(app.read_lowest(self.url, "k:s", "Lowest", ["BREAD", "MILK"], "AED"),
                         [{"item_code": "BREAD", "price_list_rate": 10}])
        path, auth = self.seen[-1]
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(path).query)
        self.assertTrue(path.startswith("/api/resource/Item%20Price?"))
        self.assertEqual(auth, "token k:s")
        self.assertEqual(json.loads(q["filters"][0]), [["price_list", "=", "Lowest"], ["item_code", "in", ["BREAD", "MILK"]],
                                                       ["currency", "=", "AED"], ["customer", "is", "not set"],
                                                       ["supplier", "is", "not set"], ["batch_no", "is", "not set"]])
        self.assertEqual(json.loads(q["fields"][0]), app.PRICE_FIELDS)
        self.assertEqual(q["limit_page_length"], ["0"])

    def test_each_chunk_s_request_line_stays_under_4_kb(self):
        codes = ["SKU/" + "/".join("ABCDE") + f"/{n:04}" for n in range(1, 400)] + ["محصول-" * 6 + f"{n:03}" for n in range(1, 60)]
        for chunk in app._chunks(codes):
            app.read_lowest(self.url, "k:s", "Lowest", chunk, "AED")
            self.assertLess(len("GET " + self.seen[-1][0] + " HTTP/1.1"), 4094)

    def test_an_answer_is_a_json_object_or_nothing(self):
        self.assertEqual(app._object(b'{"data": 1}'), {"data": 1})
        for raw in (b"", b"null", b"[]", b"[1]", b"0", b'""'):
            with self.assertRaises(ValueError):
                app._object(raw)

    def test_a_cut_answer_or_one_that_is_not_an_object_is_unreadable_never_a_crash(self):
        class Odd(BaseHTTPRequestHandler):
            def do_GET(h):
                if "Cut" in h.path:
                    h.send_response(200)
                    h.send_header("Content-Length", "100")      # promises 100 bytes, sends 5
                    h.end_headers()
                    h.wfile.write(b'{"da')
                    return
                data = {"Empty": b"", "List": b"[]", "Null": b"null", "Bare": b"{}", "NoRec": b'{"data": null}',
                        "EmptyRec": b'{"data": {}}', "Text": b'{"data": "x"}'}.get(
                    next((k for k in ("EmptyRec", "Empty", "List", "Null", "Bare", "NoRec", "Text") if "Body" + k in h.path), ""), b"[1]")
                h.send_response(200)
                h.send_header("Content-Length", str(len(data)))
                h.end_headers()
                h.wfile.write(data)

            def log_message(h, *a):
                pass

        srv = ThreadingHTTPServer(("127.0.0.1", 0), Odd)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            for call in [lambda: app.read_settings(url, "k:s", "Cut"), lambda: app.read_lowest(url, "k:s", "List", ["BREAD"], "AED")] + [
                    (lambda body=body: app.read_settings(url, "k:s", "Body" + body)) for body in ("Empty", "List", "Null", "Bare", "NoRec", "EmptyRec", "Text")]:
                with self.assertRaises(app.ShopUnreadable):
                    call()
        finally:
            srv.shutdown()
            srv.server_close()

    def test_a_refusal_or_an_answer_of_the_wrong_shape_is_unreadable(self):
        for plist in ("Shut", "Odd"):
            with self.assertRaises(app.ShopUnreadable):
                app.read_lowest(self.url, "k:s", plist, ["BREAD"], "AED")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_tgr:sub:guard": "check-a", "user:tgr@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_tgr"}, store=self.store,
                          reader=Reader({"https://shop-a.ivendnext.com": SETTINGS}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_check_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of("check/1", context([line(1, "PEN-01", rate=1)]))
        for b64 in (False, True):
            out = self.entry(self.event("/tgr/check", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual((out["statusCode"], json.loads(out["body"])["verdict"]), (200, "refuse"))
        out = self.entry(self.event("/tgr/check", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed check, and one log line that carries no shop data."""

    def test_health_a_signed_check_and_a_clean_log(self):
        log = io.StringIO()
        srv = app.make_server(app.Service(ONE, reader=Reader()), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            raw = raw_of("check/1", context([line(1, "SECRET-ITEM", rate=1)]))
            req = urllib.request.Request(base + "/tgr/check", data=raw, headers=signed(raw, CHECK), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read())["verdict"], "refuse")
            bad = urllib.request.Request(base + "/tgr/check", data=raw, headers=signed(raw, "x"), method="POST")
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(bad, timeout=5)
            self.assertEqual(e.exception.code, 401)
            e.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()
        text = log.getvalue()
        self.assertIn('"status": 200', text)
        self.assertNotIn("SECRET-ITEM", text)
        self.assertNotIn(CHECK, text)


if __name__ == "__main__":
    unittest.main()
