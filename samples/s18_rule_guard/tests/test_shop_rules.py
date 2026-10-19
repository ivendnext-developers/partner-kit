"""S18 judged by each shop's OWN rule: the shop keeps it in ``<prefix> Rule`` records, one rule each, and the service
reads them back with the user key the shop handed over on *Connect again*, after the call's signature holds, and keeps
them a minute. Two shops with different rules; a stand-in for the shop's read (``Shops``), and the real read
(``ShopApi.rules``) against a local server, so the call's shape is pinned too.

    python3 -m unittest discover -s samples/s18_rule_guard/tests -p 'test_shop_rules.py' -v
"""
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service"), str(HERE)]
sys.path.append(str(KIT / "tools" / "app_template" / "tests"))
import app  # noqa: E402
import rule  # noqa: E402
from test_service import body, context, signed  # noqa: E402
from test_shops import KEYS, make_key  # noqa: E402

LIB = "ivendnext_rgd"
NAME = f"{LIB}:sub:{app.KEY}"
A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"


def rec(kind, **f):
    return {"kind": kind, "enabled": 1, **f}


# The sample rule, as records: what test_service.RULES says in settings.
RECORDS = [rec("Members-only item", item="WINE-RESERVE"), rec("Members-only item group", item_group="Members Lounge"),
           rec("Member customer group", customer_group="Club Members"), rec("Member customer group", customer_group="Gold"),
           rec("Ask for ID at or above", amount=5000)]
# Shop B's own rule: cigars are for members, and nobody is asked for ID.
B_RECORDS = [rec("Members-only item", item="CIGAR-BOX"), rec("Member customer group", customer_group="Lounge")]


class Shops:
    """The shop's read, by the key it is made with: each key reads its own shop's records. Counts the reads."""

    def __init__(self, by_key: dict):
        self.by_key, self.reads = by_key, []

    def rules(self, url, key, prefix):
        self.reads.append((url, key, prefix))
        if key not in self.by_key:
            raise app.ShopUnreadable("the shop answered 401")
        found = self.by_key[key]
        if isinstance(found, Exception):
            raise found
        return found


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class RulesOf(unittest.TestCase):
    def test_the_records_make_the_rule(self):
        self.assertEqual(rule.rules_of(RECORDS), {"items": {"WINE-RESERVE"}, "groups": {"Members Lounge"},
                                                  "member_groups": {"Club Members", "Gold"}, "ask_above": 5000})

    def test_a_switched_off_record_is_left_out(self):
        got = rule.rules_of([{**RECORDS[0], "enabled": 0}, RECORDS[2]])
        self.assertEqual((got["items"], got["member_groups"]), (set(), {"Club Members"}))

    def test_several_id_limits_the_lowest_applies(self):
        got = rule.rules_of([rec("Ask for ID at or above", amount=900), rec("Ask for ID at or above", amount=300.5)])
        self.assertEqual(got["ask_above"], 300.5)

    def test_no_id_limit_record_means_never_ask(self):
        self.assertIsNone(rule.rules_of(B_RECORDS)["ask_above"])

    def test_an_unknown_kind_or_an_empty_link_is_left_out(self):
        got = rule.rules_of([rec("Something new", item="X"), rec("Members-only item", item=""),
                             rec("Ask for ID at or above", amount=None)])
        self.assertEqual(got, {"items": set(), "groups": set(), "member_groups": set(), "ask_above": None})

    def test_anything_but_a_list_of_records_is_refused(self):
        for bad in (None, {"data": []}, ["WINE-RESERVE"]):
            with self.assertRaises(ValueError):
                rule.rules_of(bad)

    def test_no_records_allows_every_sale(self):
        self.assertEqual(rule.decide(context(lines=(("WINE-RESERVE", "Wine"),)), rule.rules_of([])), {"verdict": "allow"})


class EachShopsOwnRule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.clock = Clock()
        self.api = Shops({"key-of-a": RECORDS, "key-of-b": B_RECORDS})
        self.svc = app.Service({"IVN_LIBRARY_APP": LIB, "IVN_SHOPS_FILE": os.path.join(self.tmp.name, "shops.json"),
                                "RGD_PREFIX": "IVENDNEXT RGD"}, api=self.api, clock=self.clock)
        self.svc.keys = KEYS
        self.connect(A, "secret-of-a", {"user:svc@a.example": "key-of-a"})
        self.connect(B, "secret-of-b", {"user:svc@b.example": "key-of-b"})

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self, site, secret, users):
        raw = json.dumps({"key": make_key(host=site, app_id=LIB), "site": site, "secrets": {NAME: secret, **users}}).encode()
        self.assertEqual(self.svc.handle("POST", "/ivendnext/connect", {"X-iVendNext-Site": site}, raw)[0], 200)

    def check(self, raw, secret, site):
        return self.svc.handle("POST", "/rgd/check", {**signed(raw, secret), "X-iVendNext-Site": site}, raw)

    def verdict(self, ctx, secret, site):
        code, out = self.check(body(ctx), secret, site)
        self.assertEqual(code, 200, out)
        return out["verdict"]

    def test_canary_each_shop_is_judged_by_its_own_records(self):
        wine, cigar = context(lines=(("WINE-RESERVE", "Wine"),)), context(lines=(("CIGAR-BOX", "Tobacco"),))
        self.assertEqual(self.verdict(wine, "secret-of-a", A), "refuse")
        self.assertEqual(self.verdict(cigar, "secret-of-a", A), "allow")
        self.assertEqual(self.verdict(wine, "secret-of-b", B), "allow")
        self.assertEqual(self.verdict(cigar, "secret-of-b", B), "refuse")
        self.assertEqual(self.verdict(context(group="Lounge", lines=(("CIGAR-BOX", "Tobacco"),)), "secret-of-b", B), "allow")
        self.assertEqual(self.verdict(context(group="Club Members", grand=600000), "secret-of-a", A), "ask")
        self.assertEqual(self.verdict(context(group="Lounge", grand=600000), "secret-of-b", B), "allow")

    def test_the_read_uses_the_shops_own_address_key_and_prefix(self):
        self.verdict(context(), "secret-of-a", A)
        self.assertEqual(self.api.reads, [(f"https://{A}", "key-of-a", "IVENDNEXT RGD")])

    def test_an_unsigned_or_forged_call_reads_nothing(self):
        raw = body()
        self.assertEqual(self.check(raw, "not-the-secret", A)[0], 401)
        self.assertEqual(self.svc.handle("POST", "/rgd/check", {"X-iVendNext-Site": A}, raw)[0], 401)
        self.assertEqual(self.api.reads, [])

    def test_a_return_that_sells_nothing_reads_nothing_and_is_allowed(self):
        ctx = context(stage="return", lines=(("WINE-RESERVE", "Wine"),))
        ctx["lines"][0]["qty_milli"] = -1000
        self.assertEqual(self.verdict(ctx, "secret-of-a", A), "allow")
        self.assertEqual(self.api.reads, [])

    def test_canary_an_exchange_that_sells_a_members_only_item_is_refused(self):
        ctx = context(stage="return", lines=(("BREAD", "Bakery"), ("WINE-RESERVE", "Wine")))
        ctx["lines"][0]["qty_milli"] = -1000          # one line back, the members-only item sold
        self.assertEqual(self.verdict(ctx, "secret-of-a", A), "refuse")
        self.assertEqual(len(self.api.reads), 1)

    def test_canary_a_key_the_shop_refuses_is_refused_in_words_that_say_so(self):
        self.api.by_key["key-of-a"] = app.KeyRefused("the shop answered 403")
        self.assertEqual(self.check(body(), "secret-of-a", A), (200, {"verdict": "refuse", "reason": app.KEY_REFUSED}))
        self.assertTrue(0 < len(app.KEY_REFUSED) <= rule.TEXT_MAX)

    def test_canary_the_rule_is_kept_a_minute_then_read_again(self):
        self.verdict(context(), "secret-of-a", A)
        self.clock.t += app.RULES_TTL - 1
        self.verdict(context(), "secret-of-a", A)
        self.assertEqual(len(self.api.reads), 1)
        self.api.by_key["key-of-a"] = B_RECORDS        # the shop changed its rule
        self.clock.t += 2
        self.assertEqual(self.verdict(context(lines=(("CIGAR-BOX", "Tobacco"),)), "secret-of-a", A), "refuse")
        self.assertEqual(len(self.api.reads), 2)

    def test_a_new_user_key_reads_again_at_once(self):
        self.verdict(context(), "secret-of-a", A)
        self.api.by_key["key-of-a2"] = B_RECORDS
        self.connect(A, "secret-of-a", {"user:svc2@a.example": "key-of-a2"})
        self.assertEqual(self.verdict(context(lines=(("CIGAR-BOX", "Tobacco"),)), "secret-of-a", A), "refuse")
        self.assertEqual([r[1] for r in self.api.reads], ["key-of-a", "key-of-a2"])

    def test_canary_a_shop_with_no_user_key_yet_is_refused_in_words_that_say_so(self):
        self.connect(A, "secret-of-a", {})
        self.assertEqual(self.check(body(), "secret-of-a", A), (200, {"verdict": "refuse", "reason": app.NOT_SET_UP}))
        self.assertEqual(self.api.reads, [])
        self.assertTrue(0 < len(app.NOT_SET_UP) <= rule.TEXT_MAX)

    def test_canary_a_shop_that_cannot_be_read_is_down_not_allowed(self):
        self.api.by_key["key-of-a"] = app.ShopUnreadable("URLError")
        self.assertEqual(self.check(body(), "secret-of-a", A), (503, {"error": "unavailable"}))
        self.api.by_key["key-of-a"] = {"not": "a list"}
        self.assertEqual(self.check(body(), "secret-of-a", A), (503, {"error": "unavailable"}))

    def test_a_failed_read_is_not_kept(self):
        self.api.by_key["key-of-a"] = app.ShopUnreadable("URLError")
        self.check(body(), "secret-of-a", A)
        self.api.by_key["key-of-a"] = RECORDS
        self.assertEqual(self.verdict(context(lines=(("WINE-RESERVE", "Wine"),)), "secret-of-a", A), "refuse")


class OneShopReadsItsShop(unittest.TestCase):
    def test_half_the_shop_settings_is_refused_at_start(self):
        for half in ({"IVN_SHOP_URL": "https://one.example"}, {"IVN_SHOP_KEY": "k:s"}):
            with self.assertRaises(SystemExit):
                app.Service({"PP_POINT_SECRET": "one", **half})

    def test_one_shop_with_a_shop_key_reads_its_records(self):
        api = Shops({"one-key": B_RECORDS})
        svc = app.Service({"PP_POINT_SECRET": "one", "IVN_SHOP_URL": "https://one.example/", "IVN_SHOP_KEY": "one-key"},
                          api=api)
        raw = body(context(lines=(("CIGAR-BOX", "Tobacco"),)))
        self.assertEqual(svc.handle("POST", "/rgd/check", signed(raw, "one"), raw)[1]["verdict"], "refuse")
        self.assertEqual(api.reads, [("https://one.example", "one-key", "PP RGD")])


class TheRealRead(unittest.TestCase):
    """``ShopApi.rules`` against a local server: the record type, the fields, the switched-on filter, every record, the
    key, and no redirect followed."""

    def setUp(self):
        self.seen, test = [], self

        class Shop(BaseHTTPRequestHandler):
            def do_GET(self):
                test.seen.append((self.path, self.headers.get("Authorization")))
                for route, code in (("/refused", 403), ("/broken", 502)):
                    if self.path.startswith(route):
                        self.send_response(code)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                if self.path.startswith("/cut"):
                    self.send_response(200)
                    self.send_header("Content-Length", "400")
                    self.end_headers()
                    self.wfile.write(b'{"')
                    return
                if self.path.startswith("/moved"):
                    self.send_response(302)
                    self.send_header("Location", "http://127.0.0.1:1/elsewhere")
                    self.end_headers()
                    return
                data = json.dumps({"data": RECORDS}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *a):
                pass

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), Shop)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.srv.server_port}"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()

    def test_the_call_shape(self):
        self.assertEqual(app.ShopApi().rules(self.url, "k:s", "IVENDNEXT RGD"), RECORDS)
        path, auth = self.seen[0]
        p = urllib.parse.urlsplit(path)
        q = dict(urllib.parse.parse_qsl(p.query))
        self.assertEqual(urllib.parse.unquote(p.path), "/api/resource/IVENDNEXT RGD Rule")
        self.assertEqual(json.loads(q["fields"]), list(rule.RULE_FIELDS))
        self.assertEqual(json.loads(q["filters"]), [["enabled", "=", 1]])
        self.assertEqual(q["limit_page_length"], "0")
        self.assertEqual(auth, "token k:s")

    def test_canary_a_cut_answer_is_the_shop_unreadable_not_a_crash(self):
        with self.assertRaises(app.ShopUnreadable):         # http.client.IncompleteRead: it says 400 bytes, sends 2
            app.ShopApi().rules(self.url + "/cut", "k:s", "IVENDNEXT RGD")

    def test_a_refused_key_is_told_apart_from_an_outage(self):
        with self.assertRaises(app.KeyRefused):
            app.ShopApi().rules(self.url + "/refused", "k:s", "IVENDNEXT RGD")
        with self.assertRaises(app.ShopUnreadable) as e:
            app.ShopApi().rules(self.url + "/broken", "k:s", "IVENDNEXT RGD")
        self.assertNotIsInstance(e.exception, app.KeyRefused)

    def test_a_redirect_is_not_followed(self):
        with self.assertRaises(app.ShopUnreadable):
            app.ShopApi().rules(self.url + "/moved", "k:s", "IVENDNEXT RGD")
        self.assertEqual(len(self.seen), 1)


if __name__ == "__main__":
    unittest.main()
