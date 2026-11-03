"""S20's hosted form: the captures answer for many sites, and a code sent by one copy is checked by another."""
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
spec = importlib.util.spec_from_file_location("s20_hosted", SAMPLE / "service" / "app.py")
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


class Captures(Base):
    def service(self, send=None):
        self.store.put(SITE, {"site": SITE, "url": f"https://{SITE}", "previous": {},
                              "secrets": {f"{APP}:sub:on_scan": "a" * 32, f"{APP}:sub:on_customer": "b" * 32, f"{APP}:sub:on_qty": "c" * 32}})
        svc = app.Hosted({"IVN_LIBRARY_APP": APP, "PP_LINE_ATTRIBUTE": "Warranty"}, self.store)
        svc.send = send
        return svc

    @staticmethod
    def body(**ctx) -> bytes:
        return json.dumps({"point": "capture/1", "context": {"v": 1, "point": "capture", **ctx}}).encode()

    def call(self, svc, path, secret, raw, **kw):
        return svc.handle("POST", path, signed(secret, raw, **kw), raw)

    def test_a_scan_is_checked_with_that_sites_secret_for_that_address(self):
        svc, raw = self.service(), self.body(event="scan", line={"item_code": "PHONE"})
        code, out = self.call(svc, "/cap/scan", "a" * 32, raw)
        self.assertEqual((code, out["verdict"]), (200, "allow"))
        self.assertEqual(out["line_attributes"][0]["name"], "Warranty")
        self.assertEqual(self.call(svc, "/cap/scan", "b" * 32, raw)[0], 401)        # another point's secret
        self.assertEqual(self.call(svc, "/cap/scan", "a" * 32, raw, site=OTHER)[0], 401)

    def test_a_code_sent_by_one_copy_is_checked_by_another_and_spent(self):
        sent = []
        first, other = self.service(lambda phone, code: sent.append((phone, code))), self.service()
        add = self.body(event="customer_add", customer={"phone": "+971 50 123"}, challenge_id="c" * 16)
        self.assertEqual(self.call(first, "/cap/customer", "b" * 32, add)[1]["verdict"], "challenge")
        wrong = self.body(event="verify", challenge_id="c" * 16, code="x")
        self.assertEqual(self.call(other, "/cap/customer", "b" * 32, wrong)[1]["verdict"], "refuse")
        right = self.body(event="verify", challenge_id="c" * 16, code=sent[0][1])
        self.assertEqual(self.call(other, "/cap/customer", "b" * 32, right)[1]["verdict"], "ok")
        self.assertEqual(self.call(other, "/cap/customer", "b" * 32, right)[1]["verdict"], "refuse")   # spent

    def test_with_no_gateway_a_customer_is_added_with_no_code(self):
        add = self.body(event="customer_add", customer={"phone": "+971 50 123"}, challenge_id="c" * 16)
        self.assertEqual(self.call(self.service(), "/cap/customer", "b" * 32, add)[1], {"verdict": "allow"})
        none = self.body(event="customer_add", customer={"phone": ""}, challenge_id="c" * 16)
        self.assertEqual(self.call(self.service(), "/cap/customer", "b" * 32, none)[1]["verdict"], "refuse")   # the manifest's word holds

    def test_a_code_in_the_store_is_never_taken_for_a_site(self):
        svc = self.service(lambda phone, code: None)
        self.call(svc, "/cap/customer", "b" * 32, self.body(event="customer_add", customer={"phone": "1"}, challenge_id="c" * 16))
        self.assertEqual(self.store.sites(), [SITE])

    def test_a_test_call_answers_with_the_points_key(self):
        svc = self.service()
        code, out = svc.handle("POST", "/cap/qty", signed("c" * 32, b"{}", test=True), b"{}")
        self.assertEqual((code, out), (200, {"test": "ok", "point": "on_qty"}))


if __name__ == "__main__":
    unittest.main()
