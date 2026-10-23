"""S48's service over the wire: the call checked with the capture's secret; on a select the shop's rules, group tree and
last right code read at the same time with the app's key (the rules and the tree kept a minute), and the code record
written BEFORE a challenge is answered; on a verify the record read and, on a right code, spent; one shop or many (the app
template's handshake); and the down cases the till turns into its down answer.

    python3 -m unittest discover -s samples/s48_customer_code_check/tests -p 'test_*.py'
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
from test_rules import CHALLENGE, RECORDS, TREE_ROWS, code_ctx, context  # noqa: E402

SECRET = "capture-secret-1"
ONE = {"IVN_CAPTURE_SECRET": SECRET, "IVN_SHOP_URL": "https://shop.example", "IVN_SHOP_KEY": "k:s"}
NOW = 1_000_000


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
    """A stand-in for the shop: rules and trees keyed by the shop's address, its code records, and every call made."""

    def __init__(self, rules=None, trees=None):
        self.rules_by = rules if rules is not None else {"https://shop.example": RECORDS}
        self.trees_by = trees if trees is not None else {"https://shop.example": TREE_ROWS}
        self.codes, self.calls = {}, []
        self.down = self.tree_down = self.write_down = self.write_unsure = False

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

    def create(self, url, key, prefix, record, timeout=None):
        self.calls.append(("create", url, key, prefix, record["challenge"], timeout))
        if self.write_down:
            raise app.ShopUnreadable("the shop answered 417")
        self.codes[record["challenge"]] = dict(record, name=record["challenge"])
        if self.write_unsure:
            raise app.WriteUnsure("TimeoutError")

    def code(self, url, key, prefix, name):
        self.calls.append(("code", url, key, prefix, name))
        if self.down:
            raise app.ShopUnreadable("down")
        rec = self.codes.get(name)
        return {k: rec.get(k) for k in app.codecheck.CODE_FIELDS} if rec else None

    def used(self, url, key, prefix, name, now):
        self.calls.append(("used", url, key, prefix, name, now))
        if self.write_down:
            raise app.ShopUnreadable("down")
        self.codes[name].update(status="Used", code="", verified_at=now)


class Clock:
    def __init__(self, t=1000.0):
        self.t = t

    def __call__(self):
        return self.t


class OneShop(unittest.TestCase):
    def setUp(self):
        self.api, self.clock, self.wall = Api(), Clock(), Clock(NOW)
        self.svc = app.Service(ONE, api=self.api, clock=self.clock, wall=self.wall)

    def call(self, ctx, secret=SECRET, ts=None):
        raw = raw_of(ctx)
        return self.svc.answer("/ccc/capture", signed(raw, secret, ts), raw)

    def test_a_customer_whose_rule_asks_gets_a_challenge_after_the_code_record_is_written(self):
        code, out = self.call(context(group="Members"))
        self.assertEqual((code, out["verdict"], out["length"]), (200, "challenge", 6))
        rec = self.api.codes[CHALLENGE]
        self.assertEqual((rec["mobile"], rec["status"], rec["sent_at"], rec["customer"]), ("+20 100 555 0147", "Sent", NOW, "CUST-1"))
        self.assertTrue(rec["code"].isdigit() and len(rec["code"]) == 6)
        self.assertNotIn(rec["code"], json.dumps(out))              # the code goes to the phone, never to the till

    def test_the_code_the_customer_reads_out_lets_them_on_once(self):
        self.call(context(group="Members"))
        given = self.api.codes[CHALLENGE]["code"]
        self.wall.t += 120
        self.assertEqual(self.call(code_ctx(given)), (200, {"verdict": "ok"}))
        self.assertEqual(self.api.codes[CHALLENGE]["status"], "Used")
        self.assertEqual(self.api.codes[CHALLENGE]["code"], "")
        self.assertIn(("used", "https://shop.example", "k:s", "PP CCC", CHALLENGE, NOW + 120), self.api.calls)
        self.assertEqual(self.call(code_ctx(given))[1], {"verdict": "refuse", "reason": app.codecheck.ENDED})

    def test_a_wrong_code_is_refused_and_spends_nothing(self):
        self.call(context(group="Members"))
        given = self.api.codes[CHALLENGE]["code"]
        wrong = f"{(int(given) + 1) % 10 ** 6:06d}"
        self.assertEqual(self.call(code_ctx(wrong))[1], {"verdict": "refuse", "reason": app.codecheck.WRONG})
        self.assertFalse(any(c[0] == "used" for c in self.api.calls))
        self.assertEqual(self.call(code_ctx(given))[1], {"verdict": "ok"})

    def test_a_code_after_ten_minutes_has_ended(self):
        self.call(context(group="Members"))
        self.wall.t += 601
        self.assertEqual(self.call(code_ctx(self.api.codes[CHALLENGE]["code"]))[1]["reason"], app.codecheck.ENDED)

    def test_a_code_check_the_shop_has_no_record_of_has_ended(self):
        self.assertEqual(self.call(code_ctx())[1], {"verdict": "refuse", "reason": app.codecheck.ENDED})

    def test_no_code_is_made_for_a_customer_the_rule_lets_on(self):
        for group in ("Retail", "Staff members"):
            self.assertEqual(self.call(context(group=group)), (200, {"verdict": "allow"}))
        self.assertEqual(self.api.codes, {})

    def test_the_same_customer_picked_again_is_asked_again(self):
        self.call(context(group="Members"))
        self.call(context(group="Members"))
        self.assertEqual(len([c for c in self.api.calls if c[0] == "create"]), 2)     # the till spent the first pass

    def test_a_code_record_saved_or_not_with_no_answer_in_time_is_still_the_code_field(self):
        self.api.write_unsure = True
        code, out = self.call(context(group="Members"))
        self.assertEqual((code, out["verdict"]), (200, "challenge"))                # never a 503 that lets them on

    def test_the_write_waits_at_most_its_own_time_and_never_past_the_budget(self):
        self.call(context(group="Members"))
        self.assertEqual([c[5] for c in self.api.calls if c[0] == "create"], [app.WRITE_TIMEOUT])
        slow = Api()
        orig = slow.rules

        def rules(*a):                          # the shop's reads take 2.5 s of the call
            self.clock.t += 2.5
            return orig(*a)
        slow.rules = rules
        svc = app.Service(ONE, api=slow, clock=self.clock, wall=self.wall)
        raw = raw_of(context(group="Members", customer="CUST-2"))
        svc.answer("/ccc/capture", signed(raw, SECRET), raw)
        self.assertEqual([c[5] for c in slow.calls if c[0] == "create"], [app.BUDGET - 2.5])
        self.clock.t += 61                      # the reads take the whole budget: the write still gets its floor
        slow2 = Api()
        slow2.rules = lambda *a: (setattr(self.clock, "t", self.clock.t + 3.2), RECORDS)[1]
        svc2 = app.Service(ONE, api=slow2, clock=self.clock, wall=self.wall)
        raw = raw_of(context(group="Members", customer="CUST-3"))
        svc2.answer("/ccc/capture", signed(raw, SECRET), raw)
        self.assertEqual([c[5] for c in slow2.calls if c[0] == "create"], [0.5])
        self.clock.t += 61                      # the till's deadline is gone: no code is written (nobody will ask for it)
        slow3 = Api()
        slow3.rules = lambda *a: (setattr(self.clock, "t", self.clock.t + 9), RECORDS)[1]
        svc3 = app.Service(ONE, api=slow3, clock=self.clock, wall=self.wall)
        raw = raw_of(context(group="Members", customer="CUST-4"))
        self.assertEqual(svc3.answer("/ccc/capture", signed(raw, SECRET), raw)[0], 503)
        self.assertEqual([c for c in slow3.calls if c[0] == "create"], [])

    def test_the_rules_and_the_tree_are_kept_a_minute(self):
        self.call(context(group="Retail"))
        self.clock.t += 59
        self.call(context(group="Retail"))
        self.assertEqual(sorted(c[0] for c in self.api.calls), ["rules", "tree"])
        self.clock.t += 2
        self.call(context(group="Retail"))
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_a_code_the_shop_cannot_save_is_a_503_so_the_down_answer_applies(self):
        self.api.write_down = True
        self.assertEqual(self.call(context(group="Members"))[0], 503)

    def test_a_right_code_the_shop_cannot_spend_is_a_503(self):
        self.call(context(group="Members"))
        given = self.api.codes[CHALLENGE]["code"]
        self.api.write_down = True
        self.assertEqual(self.call(code_ctx(given))[0], 503)

    def test_the_capture_takes_only_its_own_secret(self):
        self.assertEqual(self.call(context(), secret="wrong")[0], 401)
        self.assertEqual(self.call(code_ctx(), secret="wrong")[0], 401)
        self.assertEqual(self.api.calls, [])

    def test_an_old_timestamp_is_refused(self):
        self.assertEqual(self.call(context(), ts=time.time() - 400)[0], 401)

    def test_a_changed_body_is_refused(self):
        raw = raw_of(code_ctx("482913"))
        h = signed(raw, SECRET)
        self.assertEqual(self.svc.answer("/ccc/capture", h, raw.replace(b"482913", b"482914"))[0], 401)

    def test_a_body_it_cannot_read_is_a_400_and_reads_nothing(self):
        for ctx in ({}, dict(context(), event="customer_add"), code_ctx("1")):
            raw = json.dumps({"point": "capture/1", "context": ctx}).encode()
            self.assertEqual(self.svc.answer("/ccc/capture", signed(raw, SECRET), raw)[0], 400)
        self.assertEqual(self.api.calls, [])

    def test_an_unknown_route_is_a_404(self):
        raw = raw_of(context())
        self.assertEqual(self.svc.answer("/cbs/select", signed(raw, SECRET), raw)[0], 404)

    def test_the_shop_down_is_a_503(self):
        self.api.down = True
        self.assertEqual(self.call(context(group="Members"))[0], 503)
        self.assertEqual(self.call(code_ctx())[0], 503)
        self.assertEqual(self.api.codes, {})

    def test_the_tree_down_is_a_503_never_an_answer_from_half_the_rules(self):
        self.api.tree_down = True
        self.assertEqual(self.call(context(group="Members"))[0], 503)
        self.assertNotIn("-", self.svc.kept)

    def test_a_group_the_kept_tree_does_not_know_is_a_503_and_is_read_again(self):
        self.call(context(group="Retail"))
        self.assertEqual(self.call(context(group="Made a minute ago"))[0], 503)
        self.assertNotIn("-", self.svc.kept)
        self.call(context(group="Retail"))
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_the_prefix_names_the_record_types(self):
        svc = app.Service(dict(ONE, CCC_PREFIX="IVENDNEXT CCC"), api=self.api, clock=self.clock, wall=self.wall)
        raw = raw_of(context(group="Members"))
        svc.answer("/ccc/capture", signed(raw, SECRET), raw)
        self.assertIn(("rules", "https://shop.example", "k:s", "IVENDNEXT CCC"), self.api.calls)
        self.assertIn(("create", "https://shop.example", "k:s", "IVENDNEXT CCC", CHALLENGE, app.WRITE_TIMEOUT), self.api.calls)


class ManyShops(unittest.TestCase):
    A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        for site, n in ((self.A, "a"), (self.B, "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                "ivendnext_ccc:sub:on_select": f"check-{n}", "user:ccc@x": f"key-{n}:sec-{n}"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {"ivendnext_ccc:sub:on_select": "check-c"}})     # no user key
        self.api = Api(rules={f"https://{self.A}": RECORDS, f"https://{self.B}": []},
                       trees={f"https://{self.A}": TREE_ROWS, f"https://{self.B}": TREE_ROWS})
        self.svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_ccc", "CCC_PREFIX": "IVENDNEXT CCC"}, store=self.store,
                               api=self.api, clock=Clock(), wall=Clock(NOW))

    def call(self, secret, site, ctx=None):
        raw = raw_of(ctx or context(group="Members"))
        return self.svc.answer("/ccc/capture", signed(raw, secret, site=site), raw)

    def test_each_shop_is_answered_from_its_own_rules_with_its_own_key(self):
        self.assertEqual(self.call("check-a", self.A)[1]["verdict"], "challenge")    # A: Members asks
        self.assertEqual(self.call("check-b", self.B)[1], {"verdict": "allow"})       # B: no rules
        seen = sorted({c[1:3] for c in self.api.calls})
        self.assertEqual(seen, [(f"https://{self.A}", "key-a:sec-a"), (f"https://{self.B}", "key-b:sec-b")])

    def test_a_code_is_checked_in_the_shop_that_sent_it(self):
        self.call("check-a", self.A)
        given = self.api.codes[CHALLENGE]["code"]
        self.assertEqual(self.call("check-a", self.A, code_ctx(given))[1], {"verdict": "ok"})
        self.assertEqual([c[1] for c in self.api.calls if c[0] in ("code", "used")], [f"https://{self.A}"] * 2)

    def test_another_shops_secret_is_refused(self):
        self.assertEqual(self.call("check-b", self.A)[0], 401)
        self.assertEqual(self.call("check-a", self.B)[0], 401)

    def test_a_site_the_app_does_not_know_and_no_site_are_refused(self):
        self.assertEqual(self.call("check-a", "shop-z.ivendnext.com")[0], 401)
        self.assertEqual(self.call("check-a", None)[0], 401)

    def test_the_shops_lookup_counts_against_the_budget(self):
        clock = Clock()
        store, orig = self.store, self.store.get

        def get(site):                          # a slow shops store: 2 s before the reads start
            clock.t += 2
            return orig(site)
        store.get = get
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_ccc", "CCC_PREFIX": "IVENDNEXT CCC"}, store=store, api=self.api,
                          clock=clock, wall=Clock(NOW))
        raw = raw_of(context(group="Members"))
        svc.answer("/ccc/capture", signed(raw, "check-a", site=self.A), raw)
        self.assertEqual([c[5] for c in self.api.calls if c[0] == "create"], [app.BUDGET - 2])

    def test_a_shop_without_its_integration_key_is_a_503(self):
        self.assertEqual(self.call("check-c", "shop-c.ivendnext.com")[0], 503)
        self.assertEqual(self.call("check-c", "shop-c.ivendnext.com", code_ctx())[0], 503)

    def test_the_rules_are_kept_per_shop(self):
        self.call("check-a", self.A)
        self.call("check-b", self.B)
        self.call("check-a", self.A)
        self.assertEqual(len([c for c in self.api.calls if c[0] == "rules"]), 2)

    def test_a_new_key_reads_the_rules_again(self):
        self.call("check-a", self.A)
        self.store.put(self.A, {"site": self.A, "url": f"https://{self.A}", "secrets": {
            "ivendnext_ccc:sub:on_select": "check-a", "user:ccc@x": "key-a2:sec-a2"}})
        self.call("check-a", self.A)
        self.assertEqual([c[2] for c in self.api.calls if c[0] == "rules"], ["key-a:sec-a", "key-a2:sec-a2"])


class ShopApi(unittest.TestCase):
    """``ShopApi`` against a stand-in shop on a local port: the key, the paths, the bodies, a refusal, an error, a missing
    record, no redirect."""

    @classmethod
    def setUpClass(cls):
        cls.seen = []

        class Shop(BaseHTTPRequestHandler):
            def _reply(h, code, body):
                data = json.dumps(body).encode()
                h.send_response(code)
                h.send_header("Content-Length", str(len(data)))
                h.end_headers()
                h.wfile.write(data)

            def _body(h):
                n = int(h.headers.get("Content-Length") or 0)
                return json.loads(h.rfile.read(n)) if n else None

            def do_GET(h):
                cls.seen.append(("GET", h.path, h.headers.get("Authorization"), None))
                path = h.path.split("?", 1)[0]
                if "Redirect" in path:
                    h.send_response(302)
                    h.send_header("Location", f"http://{h.headers['Host']}/api/resource/PP%20CCC%20Rule")
                    h.end_headers()
                    return
                if path == "/api/resource/Cut%20Rule":   # an answer cut short: more promised than sent
                    h.send_response(200)
                    h.send_header("Content-Length", "100")
                    h.end_headers()
                    h.wfile.write(b'{"dat')
                    h.wfile.flush()
                    h.connection.shutdown(socket.SHUT_RDWR)
                    return
                code, body = {"/api/resource/PP%20CCC%20Rule": (200, {"data": RECORDS}),
                              "/api/resource/Customer%20Group": (200, {"data": TREE_ROWS}),
                              f"/api/resource/PP%20CCC%20Code/{CHALLENGE}": (200, {"data": {
                                  "name": CHALLENGE, "code": "482913", "status": "Sent", "sent_at": NOW, "mobile": "+20"}}),
                              "/api/resource/PP%20CCC%20Code/" + "f" * 32: (404, {"exc_type": "DoesNotExistError"}),
                              "/api/resource/Locked%20Code/" + "f" * 32: (403, {"exc_type": "PermissionError"}),
                              "/api/resource/Locked%20Rule": (403, {"exc_type": "PermissionError"}),
                              "/api/resource/Broken%20Rule": (500, {"exc_type": "x"}),
                              "/api/resource/Gone%20Rule": (404, {"exc_type": "DoesNotExistError"})}[path]
                h._reply(code, body)

            def do_POST(h):
                cls.seen.append(("POST", h.path, h.headers.get("Authorization"), h._body()))
                if "Slow" in h.path:            # the save outlasts the write's wait (a gateway that is slow to accept)
                    time.sleep(0.6)
                h._reply(417 if "Unsent" in h.path else 200, {"data": {}})

            def do_PUT(h):
                cls.seen.append(("PUT", h.path, h.headers.get("Authorization"), h._body()))
                h._reply(200, {"data": {}})

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
        return dict(urllib.parse.parse_qsl(self.seen[-1][1].split("?", 1)[1]))

    def test_reads_every_switched_on_rule_with_the_token(self):
        self.assertEqual(self.api.rules(self.url, "k:s", "PP CCC"), RECORDS)
        self.assertEqual(self.seen[-1][2], "token k:s")
        a = self.args()
        self.assertEqual((json.loads(a["filters"]), a["limit_page_length"], json.loads(a["fields"])),
                         ([["enabled", "=", 1]], "0", list(app.codecheck.RULE_FIELDS)))

    def test_reads_the_whole_group_tree(self):
        self.assertEqual(self.api.tree(self.url, "k:s"), TREE_ROWS)
        a = self.args()
        self.assertEqual((json.loads(a["fields"]), a["limit_page_length"]), (["name", "lft", "rgt"], "0"))

    def test_writes_the_code_record_with_the_token(self):
        rec = app.codecheck.code_record(context(), "482913", NOW)
        self.api.create(self.url, "k:s", "PP CCC", rec)
        method, path, auth, body = self.seen[-1]
        self.assertEqual((method, path, auth, body), ("POST", "/api/resource/PP%20CCC%20Code", "token k:s", rec))

    def test_a_write_with_no_answer_in_time_is_unsure_never_a_read(self):
        with self.assertRaises(app.WriteUnsure):
            self.api.create(self.url, "k:s", "Slow", {"challenge": CHALLENGE}, timeout=0.2)
        with self.assertRaises(app.ShopUnreadable) as e:
            self.api.create(self.url, "k:s", "Unsent", {"challenge": CHALLENGE})
        self.assertNotIsInstance(e.exception, app.WriteUnsure)

    def test_a_record_the_shop_does_not_save_is_unreadable(self):
        with self.assertRaises(app.ShopUnreadable):     # a save the shop refuses (a right not given, a rule): 417
            self.api.create(self.url, "k:s", "Unsent", {"challenge": CHALLENGE})

    def test_reads_one_code_record_and_only_its_fields(self):
        self.assertEqual(self.api.code(self.url, "k:s", "PP CCC", CHALLENGE),
                         {"name": CHALLENGE, "code": "482913", "status": "Sent", "sent_at": NOW})

    def test_a_missing_code_record_is_none_and_a_refused_one_unreadable(self):
        self.assertIsNone(self.api.code(self.url, "k:s", "PP CCC", "f" * 32))
        with self.assertRaises(app.KeyRefused):
            self.api.code(self.url, "k:s", "Locked", "f" * 32)

    def test_spends_a_right_code(self):
        self.api.used(self.url, "k:s", "PP CCC", CHALLENGE, NOW)
        self.assertEqual(self.seen[-1], ("PUT", f"/api/resource/PP%20CCC%20Code/{CHALLENGE}", "token k:s",
                                         {"status": "Used", "code": "", "verified_at": NOW}))

    def test_a_refusal_an_error_or_a_404_on_a_list_is_unreadable(self):
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
            self.api.rules("http://127.0.0.1:9", "k:s", "PP CCC")


class AsAFunction(unittest.TestCase):
    """The function entry (CitiXsys hosting): the load balancer's event in, its response out, the same answers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(self.tmp, "shops.json"))
        self.store.put("shop-a.ivendnext.com", {"site": "shop-a.ivendnext.com", "url": "https://shop-a.ivendnext.com",
                                                "secrets": {"ivendnext_ccc:sub:on_select": "check-a", "user:ccc@x": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": "ivendnext_ccc"}, store=self.store,
                          api=Api(rules={"https://shop-a.ivendnext.com": RECORDS},
                                  trees={"https://shop-a.ivendnext.com": TREE_ROWS}))
        self.entry = app.function.entry(lambda: svc, app.handle)

    def event(self, path, raw=b"", headers=None, method="POST", b64=False):
        return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in (headers or {}).items()},
                "body": base64.b64encode(raw).decode() if b64 else raw.decode(), "isBase64Encoded": b64}

    def test_health_a_signed_select_either_body_form_and_a_refusal(self):
        self.assertEqual(json.loads(self.entry(self.event("/health", method="GET"))["body"]), {"status": "ok"})
        raw = raw_of(context(group="Members"))
        for b64 in (False, True):
            out = self.entry(self.event("/ccc/capture", raw, signed(raw, "check-a", site="shop-a.ivendnext.com"), b64=b64))
            self.assertEqual(out["statusCode"], 200)
            self.assertEqual(json.loads(out["body"])["verdict"], "challenge")
        out = self.entry(self.event("/ccc/capture", raw, signed(raw, "check-b", site="shop-a.ivendnext.com")))
        self.assertEqual(out["statusCode"], 401)

    def test_the_module_entry_is_the_templates(self):
        self.assertTrue(callable(app.lambda_handler))


class OverTheWire(unittest.TestCase):
    """The real server on a local port: health, a signed select and its code, and log lines that carry no shop data,
    customer data or code."""

    def test_health_a_select_a_code_and_a_clean_log(self):
        log, api = io.StringIO(), Api()
        srv = app.make_server(app.Service(ONE, api=api), 0, log=log)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"

        def post(ctx, secret=SECRET):
            raw = raw_of(ctx)
            req = urllib.request.Request(base + "/ccc/capture", data=raw, headers=signed(raw, secret), method="POST")
            with urllib.request.urlopen(req, timeout=5) as r:
                return json.loads(r.read())
        try:
            with urllib.request.urlopen(base + "/health", timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"status": "ok"})
            self.assertEqual(post(context(group="Members", customer="SECRET-CUSTOMER"))["verdict"], "challenge")
            given = api.codes[CHALLENGE]["code"]
            self.assertEqual(post(code_ctx(given)), {"verdict": "ok"})
            with self.assertRaises(urllib.error.HTTPError) as e:
                post(context(), secret="x")
            self.assertEqual(e.exception.code, 401)
            e.exception.close()
        finally:
            srv.shutdown()
            srv.server_close()
        text = log.getvalue()
        self.assertIn('"status": 200', text)
        for secret in ("SECRET-CUSTOMER", SECRET, "+20 100 555 0147", given, CHALLENGE):
            self.assertNotIn(secret, text)


if __name__ == "__main__":
    unittest.main()
