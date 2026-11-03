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
        return app.Service({"IVN_LIBRARY_APP": APP}, self.store, lambda url, key, secret, timeout=1: tenant)

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


class SaleTenant(FakeTenant):
    """A site with two booked sales, one covered with a serial number, one of a return."""

    def __init__(self, rows, sales, why_get=None):
        super().__init__(rows, {"PHONE": "Phones"})
        self.sales, self.comments, self.why_get, self.asked = sales, [], why_get, []

    def list(self, doctype, fields, filters, order_by, limit):
        if doctype == app.TERM:
            return super().list(doctype, fields, filters, order_by, limit)
        rows = [(n, d) for n, d in self.sales.get(doctype, {}).items()]
        for field, op, value in filters:
            if op == ">=":
                rows = [(n, d) for n, d in rows if d.get(field, "") >= value]
        rows.sort(key=lambda x: x[1]["modified"], reverse="desc" in order_by)
        return [{"name": n, "modified": d["modified"]} for n, d in rows][:limit]

    def get(self, doctype, name):
        if self.why_get:
            raise app.TenantError(self.why_get)
        return self.sales[doctype][name]

    def serials_of(self, row):
        return row.get("serials") or []

    def has_our_comment(self, doctype, name):
        return False

    def add_comment(self, doctype, name, text):
        self.comments.append((doctype, name, text))
        return "C-1"


class RegisteringPass(Base):
    TODAY = "2026-11-03"
    FIRST = {"POS Invoice": "2026-11-03 09:00:00", "Sales Invoice": "2026-11-03 09:00:00"}
    PLACE = "2026-11-03 09:00:01"       # just after the site's newest sale

    def started(self, svc, site=SITE):   # the place a first pass would have taken, so a test starts from a known one
        kept = app.SiteStore(self.store, site, {}, svc.handled)
        for dt, at in self.FIRST.items():
            kept.start(dt, at)
        return svc

    def sale(self, **kw):
        return {"docstatus": 1, "posting_date": self.TODAY, "modified": f"{self.TODAY} 10:00:00",
                "items": [{"item_code": "PHONE", "serials": ["SN-1"]}], **kw}

    def service(self, tenant):
        self.store.put(SITE, {"site": SITE, "url": f"https://{SITE}", "previous": {},
                              "secrets": {f"{APP}:warranty": "s" * 32, "user:app@integration.invalid": "key:secret"}})
        return app.Service({"IVN_LIBRARY_APP": APP}, self.store, lambda url, key, secret, timeout=1: tenant)

    TERM = [{"applies_to": "Item", "item": "PHONE", "months": 24}]

    def test_a_booked_sale_gets_its_warranty_and_one_comment_and_a_second_pass_adds_none(self):
        t = SaleTenant(self.TERM, {"POS Invoice": {"S-1": self.sale()}, "Sales Invoice": {}})
        svc = self.started(self.service(t))
        out = app.scheduled(svc, "pass", 900)
        self.assertEqual(out[SITE]["POS Invoice"], 1)
        self.assertEqual(len(t.comments), 1)
        self.assertIn("SN-1", t.comments[0][2])
        self.assertIn("24 months", t.comments[0][2])
        app.scheduled(svc, "pass", 900)
        self.assertEqual(len(t.comments), 1)

    def test_a_new_copy_of_the_function_writes_no_second_comment(self):  # what was handled is on the sale
        t = SaleTenant(self.TERM, {"POS Invoice": {"S-1": self.sale()}, "Sales Invoice": {}})
        svc = self.started(self.service(t))
        app.scheduled(svc, "pass", 900)
        t.has_our_comment = lambda doctype, name: bool(t.comments)
        svc.handled.clear()
        app.scheduled(svc, "pass", 900)
        self.assertEqual(len(t.comments), 1)

    def test_the_store_keeps_one_place_per_record_type_and_no_row_per_sale(self):  # every pass scans this table
        sales = {f"S-{i}": self.sale() for i in range(30)}
        app.scheduled(self.started(self.service(SaleTenant(self.TERM, {"POS Invoice": sales, "Sales Invoice": {}}))), "pass", 900)
        rows = json.loads(open(os.path.join(self.dir.name, "shops.json")).read())
        self.assertEqual(sorted(n for n in rows if n != SITE), [f"wrc|{SITE}|mark|POS Invoice", f"wrc|{SITE}|mark|Sales Invoice"])

    def test_a_return_and_a_consolidated_invoice_get_no_comment(self):
        t = SaleTenant(self.TERM, {"POS Invoice": {"R-1": self.sale(is_return=1)}, "Sales Invoice": {"C-1": self.sale(is_consolidated=1)}})
        app.scheduled(self.started(self.service(t)), "pass", 900)
        self.assertEqual(t.comments, [])

    def test_a_sale_committed_late_with_an_older_stamp_is_still_found(self):  # tills commit out of order
        t = SaleTenant(self.TERM, {"POS Invoice": {"S-3": self.sale(modified=f"{self.TODAY} 10:00:05")}, "Sales Invoice": {}})
        svc = self.started(self.service(t))
        app.scheduled(svc, "pass", 900)
        t.sales["POS Invoice"]["S-2"] = self.sale(modified=f"{self.TODAY} 10:00:03")
        app.scheduled(svc, "pass", 900)
        self.assertEqual(sorted(c[1] for c in t.comments), ["S-2", "S-3"])

    def test_time_up_stops_the_site_and_keeps_its_place(self):
        t = SaleTenant(self.TERM, {"POS Invoice": {"S-1": self.sale()}, "Sales Invoice": {}})
        svc = self.started(self.service(t))
        out = svc.one_pass(SITE, lambda: 0)
        self.assertEqual((out["POS Invoice"], t.comments), (0, []))
        self.assertEqual(app.SiteStore(self.store, SITE, {}, svc.handled).watermark("POS Invoice", ""), self.PLACE)

    def test_two_sites_keep_their_own_places_and_a_sale_of_one_name_is_two_sales(self):
        t = SaleTenant(self.TERM, {"POS Invoice": {"S-1": self.sale()}, "Sales Invoice": {}})
        svc = self.started(self.service(t))
        self.store.put(OTHER, {"site": OTHER, "url": f"https://{OTHER}", "previous": {}, "secrets": {"user:a@integration.invalid": "k:s"}})
        self.started(svc, OTHER)
        app.scheduled(svc, "pass", 900)
        self.assertEqual(len(t.comments), 2)

    def test_one_site_down_stops_nothing_else_and_frees_its_claim(self):
        good = SaleTenant(self.TERM, {"POS Invoice": {"S-1": self.sale()}, "Sales Invoice": {}})
        class Down(FakeTenant):
            def list(self, *a):
                raise ConnectionResetError("reset")
        self.store.put(SITE, {"site": SITE, "url": f"https://{SITE}", "previous": {}, "secrets": {"user:a@integration.invalid": "k:s"}})
        self.store.put(OTHER, {"site": OTHER, "url": f"https://{OTHER}", "previous": {}, "secrets": {"user:a@integration.invalid": "k:s"}})
        svc = app.Service({"IVN_LIBRARY_APP": APP}, self.store, lambda url, key, secret, timeout=1: Down() if SITE in url else good)
        self.started(svc, OTHER)
        out = app.scheduled(svc, "pass", 900)
        self.assertEqual(out[SITE]["skipped"], "stopped")
        self.assertEqual(len(good.comments), 1)
        self.assertIsNone(self.store.get(f"wrc{shops.CLAIM_MARK}{SITE}"))

    def test_its_claim_leaves_a_feed_reader_alone(self):  # S1 with S22: a pass of S1's must not hold the loyalty app up
        svc = self.started(self.service(SaleTenant(self.TERM, {"POS Invoice": {}, "Sales Invoice": {}})))
        self.assertTrue(self.store.claim(f"pass{shops.CLAIM_MARK}{SITE}", time.time() + 900, 900))
        self.assertIn(SITE, app.scheduled(svc, "pass", 900))

    def test_a_first_pass_starts_from_that_day_and_never_comments_on_old_sales(self):
        old = self.sale(modified="2019-01-01 10:00:00", posting_date="2019-01-01")
        newest = self.sale(modified="2026-11-03 09:59:00", posting_date="2026-11-03")
        t = SaleTenant(self.TERM, {"POS Invoice": {"OLD": old, "NEWEST": newest}, "Sales Invoice": {}})
        svc = self.service(t)
        app.scheduled(svc, "pass", 900)
        self.assertEqual(t.comments, [])                                             # not even the newest from before
        app.scheduled(svc, "pass", 900)
        self.assertEqual(t.comments, [])
        t.sales["POS Invoice"]["OLD"] = {**old, "modified": "2026-11-03 10:00:00"}   # the closing saves it again
        app.scheduled(svc, "pass", 900)
        self.assertEqual(t.comments, [])
        t.sales["POS Invoice"]["NEW"] = self.sale(modified="2026-11-03 10:01:00", posting_date="2026-11-03")
        app.scheduled(svc, "pass", 900)
        self.assertEqual([c[1] for c in t.comments], ["NEW"])

    def test_a_sale_that_cannot_be_read_keeps_the_place_for_the_next_pass(self):
        t = SaleTenant(self.TERM, {"POS Invoice": {"S-1": self.sale()}, "Sales Invoice": {}}, why_get="HTTP 403")
        svc = self.started(self.service(t))
        app.scheduled(svc, "pass", 900)
        self.assertEqual(app.SiteStore(self.store, SITE, {}, svc.handled).watermark("POS Invoice", ""), self.PLACE)
        t.why_get = None
        app.scheduled(svc, "pass", 900)
        self.assertEqual(len(t.comments), 1)

    def test_a_site_that_cannot_be_read_stops_nothing_and_frees_its_claim(self):
        svc = self.service(FakeTenant(why="GET -> HTTP 403"))
        self.assertEqual(app.scheduled(svc, "pass", 900)[SITE], {"site": SITE, "skipped": "could not read"})
        self.assertEqual(self.store.sites(), [SITE])
        self.assertIsNone(self.store.get(f"wrc{shops.CLAIM_MARK}{SITE}"))

    def test_the_schedule_reaches_the_pass_through_the_function(self):
        env = {"IVN_LIBRARY_APP": APP, "IVN_SHOPS_FILE": os.path.join(self.dir.name, "shops.json")}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(app.lambda_handler({"ivn_schedule": "pass"}).get("error"), None)


if __name__ == "__main__":
    unittest.main()
