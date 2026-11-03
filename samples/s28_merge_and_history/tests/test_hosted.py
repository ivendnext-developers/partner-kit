"""S28's hosted form: a press names its site, a page's context is signed for its site, and each reads with that site's user."""
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
spec = importlib.util.spec_from_file_location("s28_hosted", SAMPLE / "service" / "app.py")
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

import history  # noqa: E402


class FakeShop:
    made = []

    def __init__(self, base, key, secret):
        self.base, self.key = base, key
        FakeShop.made.append((base, key, secret))

    def settings(self):
        return {}

    def sales(self, doctype, customer, count):
        return []

    def full_names(self, users):
        return {}


class Doors(Base):
    def service(self, user=True):
        FakeShop.made = []
        for site, a, p in ((SITE, "a" * 32, "b" * 32), (OTHER, "c" * 32, "d" * 32)):
            secrets = {f"{APP}:sub:merge": a, f"{APP}:sub:history": p}
            if user:
                secrets[f"user:{site}@integration.invalid"] = f"key-{site}:sec"
            self.store.put(site, {"site": site, "url": f"https://{site}", "previous": {}, "secrets": secrets})
        return app.Hosted({"IVN_LIBRARY_APP": APP}, self.store, FakeShop)

    @staticmethod
    def ctx(secret, nonce="n" * 32):
        raw = json.dumps({"v": 1, "nonce": nonce, "iat": int(time.time()), "exp": int(time.time()) + 300, "doctype": "Customer", "name": "C-1"},
                         sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
        return history.b64(raw) + "." + history.b64(hmac.new(secret.encode(), raw, hashlib.sha256).digest())

    def test_the_page_and_its_design_are_served(self):
        svc = self.service()
        self.assertEqual(svc.handle("GET", "/mhs/history/", {}, b"")[2], "text/html; charset=utf-8")
        self.assertEqual(svc.handle("GET", "/mhs/history/ivn-kit.css", {}, b"")[2], "text/css")

    def test_the_designs_copy_is_the_kits(self):
        kit = SAMPLE.parents[1] / "kit" / "design"
        if not kit.is_dir():
            self.skipTest("outside the kit")
        for name in ("ivn-kit.css", "ivn-kit.js"):
            self.assertEqual((SAMPLE / "service" / "design" / name).read_bytes(), (kit / name).read_bytes(), name)

    def test_a_page_reads_with_the_user_of_the_site_that_signed_it(self):
        svc = self.service()
        code, body, _ = svc.handle("POST", "/mhs/history/api/open", {}, json.dumps({"ctx": self.ctx("d" * 32)}).encode())
        self.assertEqual(code, 200, body)
        self.assertEqual(FakeShop.made, [(f"https://{OTHER}", f"key-{OTHER}", "sec")])

    def test_a_context_no_site_signed_is_refused(self):
        raw = json.dumps({"ctx": self.ctx("x" * 32)}).encode()
        self.assertEqual(self.service().handle("POST", "/mhs/history/api/open", {}, raw)[0], 403)

    def test_a_press_is_checked_with_the_sites_secret_and_a_missing_user_is_said_in_words(self):
        raw = b"{}"
        svc = self.service(user=False)
        self.assertEqual(svc.handle("POST", "/mhs/merge", signed("x" * 32, raw), raw)[0], 401)
        code, body, _ = svc.handle("POST", "/mhs/merge", signed("a" * 32, raw), raw)
        self.assertEqual(code, 200)
        self.assertIn(app.NOT_SET_UP, body.decode())

    def test_both_points_answer_a_test_call(self):
        svc = self.service()
        code, body, _ = svc.handle("POST", "/mhs/merge", signed("a" * 32, b"{}", test=True), b"{}")
        self.assertEqual((code, json.loads(body)["point"]), (200, "merge"))
        code, body, _ = svc.handle("POST", "/mhs/history/", signed("b" * 32, b"{}", test=True), b"{}")
        self.assertEqual((code, json.loads(body)["point"]), (200, "history"))
        self.assertEqual(svc.handle("POST", "/mhs/history/", signed("a" * 32, b"{}", test=True), b"{}")[0], 401)


if __name__ == "__main__":
    unittest.main()
