"""S17's hosted form: the page is served, and the context's signature says which site opened it."""
import base64
import hashlib
import hmac
import importlib.util
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

SAMPLE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SAMPLE))
for up in (SAMPLE.parents[1] / "tools" / "app_template" / "service", SAMPLE.parents[1] / "service" / "_kit"):
    sys.path.append(str(up))
spec = importlib.util.spec_from_file_location("s17_hosted", SAMPLE / "service" / "app.py")
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
import shops  # noqa: E402

APP, SITE, OTHER = "acme_one", "a.example.com", "b.example.com"


def signed(secret: str, raw: bytes, site: str = SITE, test: bool = False) -> dict:
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    head = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig, "X-iVendNext-Site": site}
    return {**head, "X-iVendNext-Test": "1"} if test else head


def event(path: str, raw: bytes = b"", headers: dict | None = None, method: str = "POST") -> dict:
    return {"httpMethod": method, "path": path, "headers": headers or {}, "body": raw.decode(), "isBase64Encoded": False}


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.store = shops.FileStore(os.path.join(self.dir.name, "shops.json"))

import page  # noqa: E402


class Board(Base):
    def service(self):
        self.posts = []
        for site, secret in ((SITE, "a" * 32), (OTHER, "b" * 32)):
            self.store.put(site, {"site": site, "url": f"https://{site}", "previous": {}, "secrets": {f"{APP}:sub:board": secret}})
        return app.Hosted({"IVN_LIBRARY_APP": APP}, self.store, lambda url, body, headers: (self.posts.append(url), (200, b"{}"))[1])

    @staticmethod
    def ctx(secret, nonce="n" * 32):
        return page.sign_context(secret, {"v": 1, "nonce": nonce, "iat": int(time.time()), "exp": int(time.time()) + 300,
                                          "store": "Main", "pos_profile": "Counter 1", "sale": {"lines": []}})

    def post(self, svc, path, **data):
        code, body, _ = svc.handle("POST", path, {}, json.dumps(data).encode())
        return code, json.loads(body)

    def test_the_page_is_served_as_a_page(self):
        code, body, ctype = self.service().handle("GET", "/board/", {}, b"")
        self.assertEqual((code, ctype), (200, "text/html; charset=utf-8"))
        self.assertIn(b"api/open", body)

    def test_the_answer_goes_to_the_site_that_opened_the_page(self):
        svc = self.service()
        self.assertEqual(self.post(svc, "/board/api/open", ctx=self.ctx("b" * 32))[0], 200)
        self.assertEqual(self.post(svc, "/board/api/answer", ctx=self.ctx("b" * 32))[0], 200)
        self.assertEqual(self.posts, [f"https://{OTHER}{app.SUBMIT}"])

    def test_a_context_no_connected_site_signed_is_refused(self):
        self.assertEqual(self.post(self.service(), "/board/api/open", ctx=self.ctx("x" * 32))[0], 403)

    def test_a_context_run_out_says_so_in_the_boards_words(self):
        old = page.sign_context("a" * 32, {"v": 1, "nonce": "o" * 32, "iat": int(time.time()) - 900, "exp": int(time.time()) - 600})
        self.assertEqual(self.post(self.service(), "/board/api/open", ctx=old)[1]["error"], "the context has run out; open the page again")

    def test_a_test_call_needs_the_sites_own_secret(self):
        svc = self.service()
        code, body, _ = svc.handle("POST", "/board/", signed("a" * 32, b"{}", test=True), b"{}")
        self.assertEqual((code, json.loads(body)["point"]), (200, "board"))
        self.assertEqual(svc.handle("POST", "/board/", signed("b" * 32, b"{}", test=True), b"{}")[0], 401)


if __name__ == "__main__":
    unittest.main()
