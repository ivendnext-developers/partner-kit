"""The template as a function (service/function.py): the load balancer's event in, the same answers out as the web
server gives. No cloud: each test builds the event the load balancer sends (headers in lower case, the body as text,
or base64 when the event says so) and calls ``app.lambda_handler``'s shape directly.

    python3 -m unittest discover -s tools/app_template/tests -p 'test_function.py' -v
"""
import base64
import io
import json
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE))
import app  # noqa: E402
import function  # noqa: E402
import shops  # noqa: E402
from test_shops import A, APP, B, KEYS, NAME, make_key, sign  # noqa: E402

SECRET = "function-secret-for-tests"
# A basket line in another script: the body is UTF-8, and the signature is over those bytes, not over ASCII.
CONTEXT = {"sale_ref": "SALE-1", "store": "Café Zürich", "customer": "Ünal", "lines": [
    {"item_code": "CAFÉ-crème", "qty": 1.0, "uom": "Nos", "luid": "l0"}]}


def event(path, raw: bytes, headers: dict, b64=False, method="POST"):
    """What the load balancer hands the function: header names in lower case, the body as text or base64."""
    return {"httpMethod": method, "path": path, "headers": {k.lower(): v for k, v in headers.items()},
            "body": base64.b64encode(raw).decode() if b64 else raw.decode("utf-8"), "isBase64Encoded": b64}


def signed(raw: bytes, secret=SECRET, site=None) -> dict:
    ts = str(int(time.time()))
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sign(secret, ts, raw), "Content-Type": "application/json"}
    return {**h, "X-iVendNext-Site": site} if site else h


def answer(out: dict) -> tuple[int, dict]:
    return out["statusCode"], json.loads(out["body"])


class OneShop(unittest.TestCase):
    def setUp(self):
        self.log = io.StringIO()
        conf = app.settings({"IVN_POINT_SECRET": SECRET})
        self.fn = function.entry(lambda: conf, lambda c, m, p, h, r: app.handle(c, m, p, h, r, self.log))
        self.raw = json.dumps({"context": CONTEXT}, ensure_ascii=False).encode("utf-8")

    def test_a_signed_press_is_answered_as_the_web_server_answers_it(self):
        code, body = answer(self.fn(event("/point/hello", self.raw, signed(self.raw))))
        self.assertEqual((code, body), (200, app.core.answer(CONTEXT)))

    def test_canary_the_bodys_exact_bytes_reach_the_signature_check(self):
        self.assertNotEqual(self.raw, self.raw.decode("utf-8").encode("ascii", "replace"))   # not plain ASCII
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw))))[0], 200)

    def test_canary_a_base64_body_is_decoded(self):
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw), b64=True)))[0], 200)

    def test_canary_headers_are_found_in_any_case(self):
        ev = event("/point/hello", self.raw, signed(self.raw))
        self.assertTrue(all(k == k.lower() for k in ev["headers"]))
        self.assertEqual(answer(self.fn(ev))[0], 200)

    def test_a_body_changed_by_one_byte_is_refused(self):
        h = signed(self.raw)
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw.replace(b"SALE-1", b"SALE-2"), h)))[0], 401)

    def test_health_and_unknown_routes(self):
        self.assertEqual(answer(self.fn(event("/health", b"", {}, method="GET"))), (200, {"status": "ok"}))
        self.assertEqual(answer(self.fn(event("/nope", b"", {}, method="GET")))[0], 404)

    def test_the_answer_is_what_the_load_balancer_expects(self):
        out = self.fn(event("/point/hello", self.raw, signed(self.raw)))
        self.assertEqual((out["isBase64Encoded"], out["headers"]["Content-Type"]), (False, "application/json"))
        self.assertIn("statusDescription", out)

    def test_settings_are_read_once_per_copy(self):
        loads = []
        fn = function.entry(lambda: loads.append(1) or app.settings({"IVN_POINT_SECRET": SECRET}), app.handle)
        for _ in range(3):
            fn(event("/health", b"", {}, method="GET"))
        self.assertEqual(len(loads), 1)

    def test_one_log_line_per_call_and_never_the_body(self):
        self.fn(event("/point/hello", self.raw, signed(self.raw)))
        lines = self.log.getvalue().strip().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertNotIn("Café", self.log.getvalue())
        self.assertNotIn(SECRET, self.log.getvalue())


class ManyShops(unittest.TestCase):
    """The handshake and a shop's own secret, through the function exactly as through the web server."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        conf = app.settings({"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": self.tmp.name + "/shops.json"})
        conf["keys"] = KEYS
        self.fn = function.entry(lambda: conf, lambda c, m, p, h, r: app.handle(c, m, p, h, r, io.StringIO()))
        self.raw = json.dumps({"context": CONTEXT}, ensure_ascii=False).encode("utf-8")
        for site, secret in ((A, "secret-of-a"), (B, "secret-of-b")):
            body = json.dumps({"key": make_key(host=site), "site": site, "secrets": {NAME: secret}}).encode()
            self.assertEqual(answer(self.fn(event("/ivendnext/connect", body, {"X-iVendNext-Site": site}))),
                             (200, {"connected": site}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_each_shop_with_its_own_secret(self):
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw, "secret-of-a", A))))[0], 200)
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw, "secret-of-b", B))))[0], 200)

    def test_canary_another_shops_secret_is_refused(self):
        # A's secret on a call naming B (and B's naming A): each refused
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw, "secret-of-a", B))))[0], 401)
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw, "secret-of-b", A))))[0], 401)

    def test_canary_a_site_that_never_connected_is_refused(self):
        h = signed(self.raw, "secret-of-a", "shop-c.ivendnext.com")
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, h)))[0], 401)

    def test_after_disconnect_the_shop_is_refused(self):
        body = json.dumps({"key": make_key(host=A), "site": A}).encode()
        self.assertEqual(answer(self.fn(event("/ivendnext/disconnect", body, {"X-iVendNext-Site": A})))[0], 200)
        self.assertEqual(answer(self.fn(event("/point/hello", self.raw, signed(self.raw, "secret-of-a", A))))[0], 401)


class Scheduled(unittest.TestCase):
    """PAYWHENUSED: a function on a schedule. The hosting calls it with {"ivn_schedule": name}; the entry hands the name
    to the app's scheduled entry, never to ``handle``. Claims keep two runs off one shop, and one day's jobs to one run."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = shops.FileStore(str(pathlib.Path(self.tmp.name) / "shops.json"))
        for site in (A, B):
            self.store.put(site, {"url": f"https://{site}", "secrets": {}})

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_scheduled_call_reaches_the_scheduled_entry_and_not_handle(self):
        seen, loads = [], []
        fn = function.entry(lambda: loads.append(1) or {"c": 1},
                            lambda *a: self.fail("handle must not answer a schedule"),
                            lambda conf, name: seen.append((conf, name)) or {A: {}, B: {}})
        with mock.patch("sys.stdout", io.StringIO()) as log:
            self.assertEqual(fn({"ivn_schedule": "pass"}), {"schedule": "pass", "shops": 2})
            fn({"ivn_schedule": "pass"})
        self.assertEqual((seen, len(loads)), ([({"c": 1}, "pass")] * 2, 1))
        self.assertIn('"schedule": "pass"', log.getvalue())

    def test_canary_an_app_with_no_scheduled_entry_answers_a_schedule_with_an_error(self):
        fn = function.entry(lambda: {}, lambda *a: self.fail("handle must not answer a schedule"))
        with mock.patch("sys.stdout", io.StringIO()):
            self.assertEqual(fn({"ivn_schedule": "pass"}), {"schedule": "pass", "error": "no scheduled entry"})

    def test_two_runs_never_work_one_shop_and_a_released_shop_is_free_again(self):
        first, second = function.Claimed(self.store, 150), function.Claimed(self.store, 150)
        self.assertEqual(sorted(first.sites()), sorted([A, B]))
        self.assertEqual(second.sites(), [])                         # both held by the first run
        self.assertEqual(sorted(self.store.sites()), sorted([A, B]))  # a claim is never listed as a shop
        first.release({A: {}})                                       # A finished, B did not
        self.assertEqual(function.Claimed(self.store, 150).sites(), [A])

    def test_canary_a_claim_left_by_a_stopped_run_is_taken_over_once_stale(self):
        now = [1000.0]
        function.Claimed(self.store, 150, clock=lambda: now[0]).sites()     # never released
        self.assertEqual(function.Claimed(self.store, 150, clock=lambda: now[0] + 100).sites(), [])
        self.assertEqual(sorted(function.Claimed(self.store, 150, clock=lambda: now[0] + 151).sites()), sorted([A, B]))

    def test_a_days_jobs_run_once_whichever_run_claims_the_day_first(self):
        day = __import__("datetime").datetime(2026, 10, 28, 3, 0)
        function.OncePerDay(self.store, day - __import__("datetime").timedelta(days=1)).get(A)
        once = function.OncePerDay(self.store, day)
        self.assertIsNone(once.get(A))                               # this run takes A's day: run the jobs
        once[A] = "2026-10-28"                                       # a container's write: ignored, the claim is the record
        self.assertEqual(function.OncePerDay(self.store, day).get(A), "2026-10-28")    # another run: skip
        self.assertIsNone(function.OncePerDay(self.store, day).get(B))
        names = json.loads((pathlib.Path(self.tmp.name) / "shops.json").read_text())
        self.assertNotIn(f"daily|{A}|2026-10-27", names)             # yesterday's claim removed


if __name__ == "__main__":
    unittest.main()
