"""S1's hosted form: the Warranty till key answers from the retailer's own terms, for many sites."""
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
from unittest import mock

SAMPLE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SAMPLE))
for up in (SAMPLE.parents[1] / "tools" / "app_template" / "service", SAMPLE.parents[1] / "service" / "_kit"):
    sys.path.append(str(up))
spec = importlib.util.spec_from_file_location("s1_hosted", SAMPLE / "service" / "hosted.py")
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


class FakeTenant:
    def __init__(self, rows=(), groups=None, why=None):
        self.rows, self.groups, self.why = list(rows), groups or {}, why

    def list(self, doctype, fields, filters, order_by, limit):
        if self.why:
            raise app.TenantError(self.why)
        return self.rows

    def item_groups(self, codes):
        return {c: self.groups[c] for c in codes if c in self.groups}


class WarrantyKey(Base):
    def service(self, tenant, user=True):
        secrets = {f"{APP}:warranty": "s" * 32, **({"user:app@integration.invalid": "key:secret"} if user else {})}
        self.store.put(SITE, {"site": SITE, "url": f"https://{SITE}", "secrets": secrets, "previous": {}})
        return app.Service({"IVN_LIBRARY_APP": APP}, self.store, lambda url, key, secret: tenant)

    def press(self, svc, lines=("PHONE",), secret="s" * 32, site=SITE):
        raw = json.dumps({"context": {"lines": [{"item_code": c, "qty": 1} for c in lines]}}).encode()
        return svc.handle("POST", app.ROUTE, signed(secret, raw, site), raw)

    def test_the_cashier_reads_the_retailers_own_term(self):
        rows = [{"applies_to": "Item", "item": "PHONE", "months": 24}, {"applies_to": "Item Group", "item_group": "Cables", "months": 3}]
        code, out = self.press(self.service(FakeTenant(rows, {"PHONE": "Phones", "CABLE": "Cables"})), ("PHONE", "CABLE"))
        self.assertEqual(code, 200)
        self.assertIn("PHONE", out["message"]["body"])
        self.assertIn("24", out["message"]["body"])
        self.assertIn("CABLE: 3 months", out["message"]["body"])

    def test_an_items_own_term_needs_no_right_on_item(self):
        class NoItems(FakeTenant):
            def item_groups(self, codes):
                raise app.TenantError("GET Item -> HTTP 403")
        code, out = self.press(self.service(NoItems([{"applies_to": "Item", "item": "PHONE", "months": 24}])))
        self.assertIn("PHONE: 24 months", out["message"]["body"])

    def test_a_call_not_signed_by_the_site_is_refused(self):
        svc = self.service(FakeTenant())
        self.assertEqual(self.press(svc, secret="x" * 32)[0], 401)
        self.assertEqual(self.press(svc, site=OTHER)[0], 401)

    def test_a_test_call_is_checked_and_answered_without_reading(self):
        svc = self.service(FakeTenant(why="must not read"))
        code, out = svc.handle("POST", app.ROUTE, signed("s" * 32, b"{}", test=True), b"{}")
        self.assertEqual((code, out), (200, {"test": "ok", "point": "warranty"}))

    def test_what_stops_it_is_said_in_words(self):
        self.assertEqual(self.press(self.service(FakeTenant(), user=False))[1]["message"]["body"], app.NOT_SET_UP)
        self.assertEqual(self.press(self.service(FakeTenant(why="GET Item -> HTTP 403")))[1]["message"]["body"], app.NO_RIGHTS)
        self.assertEqual(self.press(self.service(FakeTenant(why="timed out")))[1]["message"]["body"], app.CANNOT_READ)

    def test_it_runs_as_a_function(self):
        env = {"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": os.path.join(self.dir.name, "shops.json")}
        with mock.patch.dict(os.environ, env):
            out = app.lambda_handler(event("/health", method="GET"))
        self.assertEqual((out["statusCode"], json.loads(out["body"])), (200, {"status": "ok"}))


if __name__ == "__main__":
    unittest.main()
