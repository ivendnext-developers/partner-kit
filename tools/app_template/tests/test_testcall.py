"""The test call, the call log, --local and the point aliases of the template's service (no cloud, no shop):
    python3 -m unittest discover -s tools/app_template/tests -p 'test_testcall.py' -v
"""
import base64
import hashlib
import hmac
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent / "service")]
import app  # noqa: E402
import calllog  # noqa: E402
import core  # noqa: E402
import oneshop  # noqa: E402
import shops  # noqa: E402
import testcall  # noqa: E402

SECRET = "the-point-secret-for-tests"


def headers(body: bytes, secret=SECRET, test=True, site=None):
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "X-iVendNext-Request-Id": "req-t"}
    if test:
        h[testcall.HEADER] = "1"
    if site:
        h["X-iVendNext-Site"] = site
    return h


BODY = json.dumps({"app": "a", "key": "hello", "context": {"name": "POS-0001", "lines": []}}).encode()


class TestCall(unittest.TestCase):
    def setUp(self):
        self.conf = app.settings({"IVN_POINT_SECRET": SECRET})
        self.log = io.StringIO()
        self.ran = []
        real = core.answer
        self.addCleanup(setattr, core, "answer", real)
        core.answer = lambda ctx: (self.ran.append(ctx), real(ctx))[1]

    def call(self, path="/point/hello", h=None, body=BODY):
        return app.handle(self.conf, "POST", path, h if h is not None else headers(body), body, self.log)

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        self.assertEqual(self.call(), (200, {"test": "ok", "point": "hello"}))
        self.assertEqual(self.ran, [], "the till key's own code ran for a test call")

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        self.assertEqual(self.call(h=headers(BODY, secret="not-the-secret")), (401, {"error": "bad signature"}))
        real = app.handle(self.conf, "POST", "/point/hello", headers(BODY, secret="not-the-secret", test=False), BODY, self.log)
        self.assertEqual(self.call(h=headers(BODY, secret="not-the-secret"))[0], real[0])

    def test_canary_a_test_call_never_reaches_the_handler(self):
        status, out = self.call()
        self.assertEqual(self.ran, [])
        self.assertEqual(out, {"test": "ok", "point": "hello"})

    def test_canary_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        self.assertEqual(self.call(path="/point/nothing")[0], 404)
        self.assertEqual(self.call(path="/point/hello/extra")[0], 404)

    def test_without_the_header_the_call_is_a_real_call(self):
        status, out = self.call(h=headers(BODY, test=False))
        self.assertEqual(status, 200)
        self.assertIn("message", out)
        self.assertEqual(len(self.ran), 1)

    def test_only_the_value_1_marks_a_test(self):
        for v in ("0", "true", "", "11"):
            h = headers(BODY)
            h[testcall.HEADER] = v
            self.assertIn("message", self.call(h=h)[1], v)

    def test_connect_and_health_are_unchanged(self):
        self.assertEqual(app.handle(self.conf, "GET", "/health", {testcall.HEADER: "1"}, b"", self.log), (200, {"status": "ok"}))


class CallLog(unittest.TestCase):
    def test_each_call_is_one_line_with_the_site_the_point_the_outcome_and_the_sale(self):
        conf, log = app.settings({"IVN_POINT_SECRET": SECRET}), io.StringIO()
        app.handle(conf, "POST", "/point/hello", headers(BODY, test=False), BODY, log)
        app.handle(conf, "POST", "/point/hello", headers(BODY), BODY, log)
        app.handle(conf, "POST", "/point/hello", headers(BODY, secret="x", test=False), BODY, log)
        lines = [json.loads(l) for l in log.getvalue().splitlines()]
        self.assertEqual([l["outcome"] for l in lines], ["answered", "test", "refused"])
        self.assertEqual(lines[0]["point"], "a till key (hello)")
        self.assertEqual(lines[0]["record"], "sale POS-0001")
        self.assertIn("a till key (hello) · answered in", lines[0]["text"])
        self.assertNotIn(SECRET, log.getvalue())

    def test_the_line_never_carries_the_customer_or_an_item(self):
        self.assertIsNone(calllog.record_of({"customer": "Jane Doe", "item_code": "SKU-1"}))
        self.assertEqual(calllog.record_of({"invoice": "POS-9"}), "sale POS-9")

    def test_the_words_logs_shows(self):
        import datetime
        line = json.loads(calllog.line("retailer.ivendnext.com", calllog.plain("check"), 200, 0.31, "sale POS-0001",
                                       now=datetime.datetime(2026, 10, 31, 14, 31, tzinfo=datetime.timezone.utc)))
        self.assertEqual(line["text"], "14:31 · retailer.ivendnext.com · a check at Pay · answered in 0.31 s · sale POS-0001")


class Aliases(unittest.TestCase):
    def tearDown(self):
        shops.ALIASES.clear()

    def test_a_combined_apps_point_is_found_under_its_tagged_name(self):
        record = {"secrets": {"acme_hk:sub:tgr_guard": "s1"}, "previous": {}}
        self.assertEqual(shops.secrets_for(record, "acme_hk:sub:guard"), [])
        shops.ALIASES.update({"guard": "tgr_guard"})
        self.assertEqual(shops.secrets_for(record, "acme_hk:sub:guard"), [b"s1"])
        self.assertEqual(testcall.answer("guard"), (200, {"test": "ok", "point": "tgr_guard"}))

    def test_no_alias_changes_nothing(self):
        record = {"secrets": {"a:k": "s"}, "previous": {"a:k": "o"}}
        self.assertEqual(shops.secrets_for(record, "a:k"), [b"s", b"o"])


class OneShop(unittest.TestCase):
    def test_the_fallback_names_every_missing_setting(self):
        with self.assertRaises(SystemExit) as e:
            oneshop.settings({"IVN_CHECK_SECRET": " s "}, ["IVN_CHECK_SECRET", "IVN_SHOP_URL", "IVN_SHOP_KEY"])
        self.assertIn("IVN_SHOP_URL, IVN_SHOP_KEY", str(e.exception))
        self.assertEqual(oneshop.settings({"A": " x "}, ["A"], ["B"]), {"A": "x", "B": ""})
        self.assertTrue(oneshop.many({"IVN_LIBRARY_APP": "acme_hk"}))
        self.assertFalse(oneshop.many({}))


class Local(unittest.TestCase):
    def test_local_reads_env_local_answers_on_8000_and_takes_the_test_secret(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, ".env.local").write_text("# test values\nIVN_TEST_SECRET=local-test-secret\n")
            env = app.local_env(d, {})
            self.assertEqual((env["PORT"], env["IVN_POINT_SECRET"]), ("8000", "local-test-secret"))
            conf = app.settings(env)
            self.assertEqual(app.handle(conf, "POST", "/point/hello", headers(BODY, secret="local-test-secret"), BODY,
                                        io.StringIO()), (200, {"test": "ok", "point": "hello"}))

    def test_local_without_a_test_secret_says_where_to_write_one(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SystemExit) as e:
            app.local_env(d, {})
        self.assertIn("IVN_TEST_SECRET", str(e.exception))

    def test_the_service_runs_with_local_and_answers_a_signed_test_call(self):
        with tempfile.TemporaryDirectory() as d:
            folder = pathlib.Path(d)
            (folder / "service").mkdir()
            for f in (HERE.parent / "service").glob("*.py"):
                (folder / "service" / f.name).write_bytes(f.read_bytes())
            (folder / ".env.local").write_text("IVN_TEST_SECRET=local-test-secret\nPORT=0\n")
            # PORT=0 in .env.local is overridden by a free port we choose
            import socket
            with socket.socket() as s:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            p = subprocess.Popen([sys.executable, "-I", str(folder / "service" / "app.py"), "--local"],
                                 env={"PORT": str(port), "PATH": os.environ.get("PATH", "")},
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            def stop():
                p.kill()
                p.communicate()
            self.addCleanup(stop)
            self.assertIn('"listening"', p.stdout.readline())
            req = urllib.request.Request(f"http://127.0.0.1:{port}/point/hello", data=BODY, method="POST",
                                         headers=headers(BODY, secret="local-test-secret"))
            with urllib.request.urlopen(req, timeout=5) as r:
                self.assertEqual(json.loads(r.read()), {"test": "ok", "point": "hello"})


if __name__ == "__main__":
    unittest.main()
