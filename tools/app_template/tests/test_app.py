"""The template service, with no cloud and no shop: run
    python3 -m unittest discover -s tools/app_template/tests -p 'test_*.py' -v
"""
import base64
import hashlib
import hmac
import io
import json
import os
import pathlib
import sys
import threading
import time
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[2]                                         # the kit's root
sys.path[:0] = [str(HERE.parent / "service"), str(ROOT / "tools" / "contracts")]
import app  # noqa: E402
import core  # noqa: E402

try:
    import check  # noqa: E402  (the published contracts; present in the kit, absent if you copied only this folder)
except ImportError:
    check = None

SECRET, OLD = "current-secret-for-tests", "previous-secret-for-tests"
CONTEXT = {"sale_ref": "SALE-1", "store": "Demo Retail — Store 1", "customer": "Walk-in", "lines": [
    {"item_code": "A", "qty": 1.0, "uom": "Nos", "luid": "l0"}, {"item_code": "B", "qty": 2.0, "uom": "Nos", "luid": "l1"}]}


def sign(secret, ts, body):
    return base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).digest()).decode()


class Service(unittest.TestCase):
    def setUp(self):
        self.log = io.StringIO()
        conf = app.settings({"IVN_POINT_SECRET": SECRET, "IVN_POINT_SECRET_PREVIOUS": OLD})
        self.srv = app.make_server(conf, port=0, log=self.log)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)

    def post(self, path="/point/hello", payload=None, secret=SECRET, ts=None, sig=None, raw=None):
        body = raw if raw is not None else json.dumps(payload or {"app": "a", "key": "k", "returns": ["message"], "context": CONTEXT}).encode()
        ts = ts or str(int(time.time()))
        req = urllib.request.Request(self.base + path, data=body, method="POST", headers={
            "X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig if sig is not None else sign(secret, ts, body),
            "X-iVendNext-Request-Id": "req-1", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            with e:
                return e.code, json.loads(e.read())

    def test_health_answers_without_a_signature(self):
        with urllib.request.urlopen(self.base + "/health", timeout=5) as r:
            self.assertEqual((r.status, json.loads(r.read())), (200, {"status": "ok"}))

    def test_a_signed_call_gets_the_cores_answer(self):
        code, out = self.post()
        self.assertEqual((code, out), (200, core.answer(CONTEXT)))
        self.assertEqual(out["message"]["body"], "This sale has 2 lines.")

    def test_the_answer_holds_the_published_contract(self):
        if check is None:
            self.skipTest("the contracts folder is not beside this folder")
        for ctx in (CONTEXT, {"lines": []}, {}):
            self.assertEqual(check.errors("remote_till_key", "answer", core.answer(ctx)), [])

    def test_a_wrong_signature_a_stale_time_and_a_missing_header_are_refused(self):
        self.assertEqual(self.post(secret="someone-elses-secret")[0], 401)
        self.assertEqual(self.post(ts=str(int(time.time()) - 301))[0], 401)
        self.assertEqual(self.post(sig="")[0], 401)
        self.assertEqual(self.post(raw=b'{"context": {}}', sig="not-a-signature")[0], 401)

    def test_the_old_secret_is_accepted_while_you_rotate_and_nothing_else_is(self):
        self.assertEqual(self.post(secret=OLD)[0], 200)
        self.assertEqual(self.post(secret="a-third-secret")[0], 401)

    def test_an_oversize_body_and_a_wrong_route_are_refused(self):
        self.assertEqual(self.post(raw=b"x" * (app.BODY_MAX + 1))[0], 413)
        self.assertEqual(self.post(path="/point/other")[0], 404)

    def test_a_signed_body_that_is_not_a_call_is_a_400_not_a_crash(self):
        self.assertEqual(self.post(raw=b"not json")[0], 400)
        self.assertEqual(self.post(raw=b"[]")[0], 400)

    def test_the_log_has_one_line_per_call_and_never_the_shops_data_or_secrets(self):
        self.post()
        self.post(secret="someone-elses-secret")
        text = self.log.getvalue()
        lines = [json.loads(l) for l in text.strip().splitlines()]
        self.assertEqual([l["status"] for l in lines], [200, 401])
        for leak in ("Demo Retail", "Walk-in", "SALE-1", SECRET, OLD, "someone-elses-secret", "X-iVendNext-Signature"):
            self.assertNotIn(leak, text)

    def test_it_does_not_start_without_its_secret(self):
        for env in ({}, {"IVN_POINT_SECRET": ""}, {"IVN_POINT_SECRET": "   "}):
            with self.assertRaises(SystemExit):
                app.settings(env)
        self.assertEqual(app.settings({"IVN_POINT_SECRET": "s", "PORT": "9000"})["port"], 9000)
        self.assertEqual(len(app.settings({"IVN_POINT_SECRET": "s"})["secrets"]), 1)


class Core(unittest.TestCase):
    def test_the_core_needs_no_server(self):
        self.assertEqual(core.answer({"lines": []})["message"]["body"], "There are no items on this sale yet.")
        self.assertEqual(core.answer({"lines": [{}]})["message"]["body"], "This sale has 1 line.")
        m = core.answer(None)["message"]
        self.assertTrue(0 < len(m["title"]) <= core.TITLE_MAX and 0 < len(m["body"]) <= core.BODY_MAX)


if __name__ == "__main__":
    unittest.main()
