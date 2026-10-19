"""S18 serving many shops, as a function (app.json "runs": "function"): each shop connects itself with its library key
(the app template's handshake) and each check is verified with THAT shop's own secret, "<app>:sub:guard", and judged by
THAT shop's own Rule records (a stand-in for the shop's read: ``test_shop_rules.Shops``). The events
are the load balancer's (header names in lower case, the body as text or base64), handed to ``app.lambda_handler``'s
shape with the test's own library keys.

    python3 -m unittest discover -s samples/s18_rule_guard/tests -p 'test_many_shops.py' -v
"""
import base64
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
KIT = HERE.parents[2]
sys.path[:0] = [str(HERE.parent), str(HERE.parent / "service"), str(HERE)]
sys.path.append(str(KIT / "tools" / "app_template" / "tests"))
import app  # noqa: E402
import function  # noqa: E402
from test_service import RULES, body, context, signed  # noqa: E402
from test_shop_rules import RECORDS, Shops  # noqa: E402
from test_shops import KEYS, make_key  # noqa: E402

LIB = "ivendnext_rgd"
NAME = f"{LIB}:sub:{app.KEY}"
A, B = "shop-a.ivendnext.com", "shop-b.ivendnext.com"


def event(path, raw: bytes, headers: dict, b64=False, method="POST"):
    return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in headers.items()},
            "body": base64.b64encode(raw).decode() if b64 else raw.decode("utf-8"), "isBase64Encoded": b64}


def answer(out: dict):
    return out["statusCode"], json.loads(out["body"])


class ManyShops(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.api = Shops({"key-of-a": RECORDS, "key-of-b": RECORDS})
        svc = app.Service({"IVN_LIBRARY_APP": LIB, "IVN_SHOPS_FILE": os.path.join(self.tmp.name, "shops.json")}, api=self.api)
        svc.keys = KEYS
        self.fn = function.entry(lambda: svc, app.handle)
        for site, secret, user in ((A, "secret-of-a", "key-of-a"), (B, "secret-of-b", "key-of-b")):
            raw = json.dumps({"key": make_key(host=site, app_id=LIB), "site": site,
                              "secrets": {NAME: secret, "user:svc@example.com": user}}).encode()
            self.assertEqual(answer(self.fn(event("/ivendnext/connect", raw, {"X-iVendNext-Site": site}))),
                             (200, {"connected": site}))

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, raw, secret, site, b64=False):
        return answer(self.fn(event("/rgd/check", raw, {**signed(raw, secret), "X-iVendNext-Site": site}, b64=b64)))

    def test_the_three_answers_for_a_connected_shop(self):
        self.assertEqual(self.check(body(), "secret-of-a", A), (200, {"verdict": "allow"}))
        refused = self.check(body(context(lines=(("WINE-RESERVE", "Wine"),))), "secret-of-a", A)
        self.assertEqual((refused[0], refused[1]["verdict"]), (200, "refuse"))
        asked = self.check(body(context(group="Club Members", grand=600000)), "secret-of-b", B)
        self.assertEqual((asked[0], asked[1]["verdict"]), (200, "ask"))

    def test_canary_the_check_reads_the_route_secret_of_the_shop_it_names(self):
        self.assertEqual(self.check(body(), "secret-of-a", B)[0], 401)
        self.assertEqual(self.check(body(), "secret-of-b", A)[0], 401)

    def test_canary_a_site_that_never_connected_is_refused(self):
        self.assertEqual(self.check(body(), "secret-of-a", "shop-c.ivendnext.com")[0], 401)

    def test_a_call_naming_no_site_is_refused(self):
        raw = body()
        self.assertEqual(answer(self.fn(event("/rgd/check", raw, signed(raw, "secret-of-a"))))[0], 401)

    def test_a_key_for_the_sample_not_the_library_app_is_refused(self):
        raw = json.dumps({"key": make_key(host=A, app_id="pp_rgd"), "site": A, "secrets": {NAME: "x"}}).encode()
        self.assertEqual(answer(self.fn(event("/ivendnext/connect", raw, {"X-iVendNext-Site": A}))),
                         (403, {"refused": "key_other_app"}))

    def test_after_disconnect_the_shop_is_refused(self):
        raw = json.dumps({"key": make_key(host=A, app_id=LIB), "site": A}).encode()
        self.assertEqual(answer(self.fn(event("/ivendnext/disconnect", raw, {"X-iVendNext-Site": A})))[0], 200)
        self.assertEqual(self.check(body(), "secret-of-a", A)[0], 401)

    def test_a_basket_in_another_script_and_a_base64_body(self):
        raw = json.dumps({"point": "check/1", "context": context(lines=(("CAFÉ-crème", "Épicerie"),))},
                         ensure_ascii=False).encode("utf-8")
        self.assertEqual(self.check(raw, "secret-of-a", A), (200, {"verdict": "allow"}))
        self.assertEqual(self.check(raw, "secret-of-a", A, b64=True), (200, {"verdict": "allow"}))

    def test_a_body_changed_by_one_byte_is_refused(self):
        raw = body()
        h = {**signed(raw, "secret-of-a"), "X-iVendNext-Site": A}
        self.assertEqual(answer(self.fn(event("/rgd/check", raw.replace(b"s-1", b"s-2"), h)))[0], 401)

    def test_health_as_a_function(self):
        self.assertEqual(answer(self.fn(event("/health", b"", {}, method="GET"))), (200, {"ok": 1}))


class OneShopUnchanged(unittest.TestCase):
    def test_one_shop_mode_needs_no_store_and_checks_its_one_secret(self):
        svc = app.Service({"PP_POINT_SECRET": "one", **RULES})
        self.assertIsNone(svc.store)
        raw = body()
        self.assertEqual(svc.handle("POST", "/rgd/check", signed(raw, "one"), raw), (200, {"verdict": "allow"}))
        self.assertEqual(svc.handle("POST", "/rgd/check", signed(raw, "two"), raw)[0], 401)
        self.assertEqual(svc.handle("POST", "/ivendnext/connect", {}, b"{}")[0], 404)   # no handshake for one shop


if __name__ == "__main__":
    unittest.main()
