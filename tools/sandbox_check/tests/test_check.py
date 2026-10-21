"""Laptop tests of the sandbox check, no site: the whole script — its own requests and the request collection's runner
(curl and jq) — against a local stand-in that answers with a good site's recorded answers, then with each planted fault.

    python3 -m unittest discover -s tools/sandbox_check/tests -p 'test_*.py'
"""

import copy
import io
import json
import os
import shutil
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import check as C  # noqa: E402

with open(os.path.join(HERE, "answers_good.json")) as _f:
    GOOD = json.load(_f)
KEY, SECRET, NAME = "k1", "s1", "demo.sandbox.test"


class StandIn(ThreadingHTTPServer):
    """Answers by path; refuses a wrong key (401) and a request that lost the site's name (421)."""

    def __init__(self, answers):
        self.answers = answers
        super().__init__(("127.0.0.1", 0), Handler)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if not self.headers.get("Host", "").startswith(NAME):
            status, body = 421, {"exc_type": "SiteNotFound"}
        elif path != "/api/method/ping" and self.headers.get("Authorization") != f"token {KEY}:{SECRET}":
            status, body = 401, {"exc_type": "AuthenticationError"}
        else:
            status, body = self.server.answers.get(path, [404, {"exc_type": "DoesNotExistError"}])
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


class SandboxCheck(unittest.TestCase):
    def run_check(self, answers, secret=SECRET, extra=()):
        srv = StandIn(answers)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        port = srv.server_address[1]
        env = {k: os.environ.get(k) for k in ("BASE", "KEY", "SECRET")}
        os.environ.update(BASE=f"http://{NAME}:{port}", KEY=KEY, SECRET=secret)
        out = io.StringIO()
        try:
            code = C.main(["--connect-to", f"127.0.0.1:{port}", *extra], out=out)
        finally:
            srv.shutdown()
            srv.server_close()
            for k, v in env.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        return code, out.getvalue()

    def assertFails(self, out, label):
        self.assertIn(f"FAIL  {label}", out)
        self.assertIn("SANDBOX CHECK RED", out.splitlines()[-1])

    @unittest.skipUnless(shutil.which("curl") and shutil.which("jq"), "the collection's runner needs curl and jq")
    def test_good_site_is_green(self):
        code, out = self.run_check(GOOD)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[-1], "SANDBOX CHECK GREEN — 9 of 9 passed")

    def test_wrong_key_is_red(self):
        code, out = self.run_check(GOOD, secret="not-the-secret")
        self.assertEqual(code, 1)
        self.assertIn("PASS  the site answers", out)          # the site is up; only the key is wrong
        self.assertFails(out, "your key signs in")

    def test_missing_store_is_red(self):
        a = copy.deepcopy(GOOD)
        a["/api/resource/Warehouse"][1]["data"] = [w for w in a["/api/resource/Warehouse"][1]["data"]
                                                   if not w["name"].startswith("Demo Retail — Store 3")]
        code, out = self.run_check(a)
        self.assertEqual(code, 1)
        self.assertFails(out, "3 stores, each with one till profile")

    def test_store_without_till_profile_is_red(self):
        a = copy.deepcopy(GOOD)
        a["/api/resource/POS%20Profile"][1]["data"].pop()
        code, out = self.run_check(a)
        self.assertFails(out, "3 stores, each with one till profile")

    def test_a_shop_on_an_older_release_is_told_to_update(self):
        a = copy.deepcopy(GOOD)
        for name in ("get_logged_user", "get_versions"):     # what the shop answers for a call it does not know
            a[f"/api/method/ivendnext_mpos.api.v1.{name}"] = [417, {"exc_type": "ValidationError", "exception":
                f"ValidationError: Failed to get method for command ivendnext_mpos.api.v1.{name} with No module"}]
        code, out = self.run_check(a)
        self.assertEqual(code, 1)
        self.assertIn("FAIL  your key signs in — " + C.OLD_RELEASE, out)
        self.assertIn("FAIL  the POS apps are installed — " + C.OLD_RELEASE, out)

    def test_site_without_the_pos_app_is_red(self):
        a = copy.deepcopy(GOOD)
        for app in ("ivendnext_pos", "ivendnext_mpos"):
            del a["/api/method/ivendnext_mpos.api.v1.get_versions"][1]["message"][app]
        a["/api/resource/DocType"][1]["data"] = []
        code, out = self.run_check(a)
        self.assertEqual(code, 1)
        self.assertFails(out, "the POS apps are installed")
        self.assertFails(out, "the extension points' record types")

    def test_site_without_the_install_screen_is_red(self):
        a = copy.deepcopy(GOOD)
        del a["/api/method/ivendnext_mpos.api.extension_package.holders"]  # the method does not exist: an error, not a list
        code, out = self.run_check(a)
        self.assertEqual(code, 1)
        self.assertFails(out, "the install screen (for tools/deploy)")

    def test_integration_user_with_admin_rights_is_red(self):
        a = copy.deepcopy(GOOD)
        a["/api/resource/User/integration%40demo-retail.example"][1]["data"]["roles"].append({"role": "System Manager"})
        code, out = self.run_check(a)
        self.assertFails(out, "the integration user")

    def test_record_carries_no_secret(self):
        path = os.path.join(HERE, "_record.tmp.json")
        try:
            self.run_check(GOOD, extra=["--record", path])
            with open(path) as fh:
                raw = fh.read()
            self.assertIn("/api/resource/Warehouse", json.loads(raw))
            self.assertNotIn(SECRET, raw.replace("SECRET", ""))
            self.assertNotIn(f"token {KEY}", raw)
        finally:
            os.path.exists(path) and os.remove(path)

    def test_missing_settings_refused(self):
        env = {k: os.environ.pop(k, None) for k in ("BASE", "KEY", "SECRET")}
        try:
            self.assertEqual(C.main([], out=io.StringIO()), 2)
        finally:
            os.environ.update({k: v for k, v in env.items() if v is not None})

    def test_https_names_the_site_not_the_address(self):
        """--connect-to over HTTPS: TLS is told the SITE's name (SNI + certificate), not the address dialled. The
        stand-in above speaks plain HTTP only, so this leg is tested here, on the connection itself."""
        seen = {}

        class Ctx:
            def wrap_socket(self, sock, server_hostname=None):
                seen["sni"] = server_hostname
                return sock

        conn = C._SiteHttps("10.0.0.5", 443, "demo.sandbox.test", context=Ctx())
        real = C.http.client.HTTPConnection.connect
        C.http.client.HTTPConnection.connect = lambda self: setattr(self, "sock", object())
        try:
            conn.connect()
        finally:
            C.http.client.HTTPConnection.connect = real
        self.assertEqual(seen["sni"], "demo.sandbox.test")
        site_conn = C.Site("https://demo.sandbox.test", "k", "s", "10.0.0.5:443")._conn()
        self.assertIsInstance(site_conn, C._SiteHttps)          # the check's own requests use it
        self.assertEqual((site_conn.host, site_conn.site_name), ("10.0.0.5", "demo.sandbox.test"))

    def test_point_types_match_the_installer(self):
        # The installer lives in the POS app since row DEPLOY (business_logic/manifest_install.py, POINT_DT), which a
        # laptop does not have, so its list is pinned here as read at iVendNext_PWA development 7d47d331a — re-read it at
        # each re-pin of the kit's checker copy (tools/manifest/validate.py names the same commit).
        point_dt = {"extension_subscriptions": "Retail Extension Subscription", "desk_actions": "Retail Desk Action",
                    "save_rules": "Retail Save Rule", "fiscal_readers": "Retail Fiscal Reader"}
        self.assertIn("7d47d331a203fd8b2794f83270a4190b3c1908e8",
                      open(os.path.join(HERE, "..", "..", "manifest", "validate.py")).read(1000))
        self.assertEqual(sorted(C.POINT_TYPES), sorted([*point_dt.values(), "Retail Extension Log"]))


if __name__ == "__main__":
    unittest.main()
