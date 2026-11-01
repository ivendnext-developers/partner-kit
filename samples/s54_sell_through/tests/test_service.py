"""S54's laptop tests: the real service, a stand-in for the retailer's record API and ``run_report``, and presses
signed exactly as the retailer signs them (base64 HMAC-SHA256 of ``<timestamp>.<body>``, sorted-key compact JSON).

    python3 -m unittest discover -s samples/s54_sell_through/tests -p 'test_*.py'

On our test bench the real Desk button was pressed on a real run over real till sales and stock; these prove the
service's own duties fast, and are what the mutation canary turns RED. The signing helpers and the many-retailer shape
are S49's (``samples/s49_post_sale_feedback/tests/test_service.py``): a defect here is a defect there."""

import base64
import copy
import datetime
import hashlib
import hmac
import json
import os
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.dirname(HERE), os.path.join(os.path.dirname(HERE), "service"), HERE]
import app  # noqa: E402
import shops  # noqa: E402
import sst  # noqa: E402
from test_core import COLOUR, SIZE, item_rows, run_doc  # noqa: E402

SECRET = "s54-work-secret"
URL, SITE = "https://shop.example", "shop.example"
NOW = datetime.datetime(2026, 10, 29, 18, 0, tzinfo=datetime.timezone.utc).timestamp()
CONF = {"IVN_SHOP_URL": URL, "IVN_SHOP_KEY": "k:s", "IVN_WORK_SECRET": SECRET}
POS_COLS = ["store", "pos", "item", "item_name", "sales", "refund", "discount", "net_sales", "unit_solds", "net_tax",
            "item_surcharge"]
SPQ_COLS = [{"fieldname": f} for f in ("item_code", "item_name", "description", "item_group", "brand", "warehouse",
                                       "stock_uom", "actual_qty", "planned_qty", "indented_qty", "ordered_qty",
                                       "reserved_qty", "reserved_qty_for_production", "reserved_qty_for_production_plan",
                                       "reserved_qty_for_sub_contract", "reserved_qty_for_pos", "projected_qty",
                                       "re_order_level", "re_order_qty", "shortage_qty")]


def spq_row(item, store, actual, pos=0):
    r = [None] * len(SPQ_COLS)
    r[0], r[5], r[7], r[15] = item, store, actual, pos
    return r


SOLD = {"Mall - DR": [["Mall - DR", "P", "DRESS-A-RED-S", "x", 0, 0, 0, 0, 3, 0, 0],
                      ["Mall - DR", "P", "DRESS-A-RED-L", "x", 0, 0, 0, 0, 1, 0, 0],
                      ["Mall - DR", "P", "SCARF", "x", 0, 0, 0, 0, 9, 0, 0]],
        "High Street - DR": [["High Street - DR", "P", "DRESS-A-RED-S", "x", 0, 0, 0, 0, 1, 0, 0]]}
STOCK = {"Mall - DR": [spq_row("DRESS-A-RED-S", "Mall - DR", 1, 1), spq_row("DRESS-A-RED-L", "Mall - DR", 4),
                       spq_row("DRESS-B-BLA-M", "Mall - DR", 6)],
         "High Street - DR": [spq_row("DRESS-A-RED-S", "High Street - DR", 2)]}


def _match(row, filters):
    for f, op, v in filters:
        x = row.get(f)
        if op == "=" and x != v or op == "is" and (v == "set") != bool(x):
            return False
        if op not in ("=", "is"):
            raise AssertionError(f"the stand-in does not know the operator {op}")
    return True


class FakeTenant:
    """The retailer's record API and its two reports, and every call."""

    def __init__(self, run=None):
        self.runs = {"SST-00001": run or run_doc()}
        self.items = [dict(r, item_group="Dresses", disabled=0) for r in item_rows()]
        self.attributes = {"Size": SIZE, "Colour": COLOUR}
        self.sold, self.stock = copy.deepcopy(SOLD), copy.deepcopy(STOCK)
        self.calls, self.writes, self.refuse = [], [], None

    def _check(self, kind):
        self.calls.append(kind)
        if self.refuse:
            raise app.TenantError("refused", self.refuse)

    def doc(self, doctype, name, timeout=None):
        self._check(("doc", doctype, name))
        src = self.runs if doctype == sst.RUN else self.attributes if doctype == "Item Attribute" else {}
        if name not in src:
            raise app.TenantError("not found", 404)
        return copy.deepcopy(src[name])

    def rows(self, doctype, fields, filters, timeout=None, limit=0):
        self._check(("rows", doctype, json.dumps(filters), limit))
        assert doctype == "Item" and fields == app.ITEM_FIELDS
        return [{k: r.get(k) for k in ("name", "variant_of", "attribute", "attribute_value")}
                for r in self.items if _match(r, filters)][: limit or None]

    def report(self, name, filters, timeout=None):
        self._check(("report", name, json.dumps(filters, sort_keys=True)))
        if name == sst.POS_SALE_REPORT:
            return {"message": {"columns": POS_COLS, "result": copy.deepcopy(self.sold.get(filters["warehouse"], []))}}
        if name == sst.STOCK_REPORT:
            return {"message": {"columns": SPQ_COLS, "result": copy.deepcopy(self.stock.get(filters["warehouse"], []))}}
        raise app.TenantError("no such report", 404)

    def update(self, doctype, name, body, timeout=None):
        self._check(("update", doctype, name))
        self.writes.append((doctype, name, copy.deepcopy(body)))
        self.runs[name].update(body)
        return self.runs[name]


def body(names=("SST-00001",), doctype=None):
    recs = [{"doctype": doctype or sst.RUN, "name": n, "fields": {"name": n}} for n in names]
    ctx = {"v": 1, "action": "a1", "label": "Work out sell-through", "user": "buyer@shop.example", "lang": "en",
           "idempotency_key": "k1", "inputs": {}, "records": recs}
    return json.dumps({"point": "desk_action/1", "context": ctx}, sort_keys=True, separators=(",", ":")).encode()


def signed(raw, secret=SECRET, ts=None, site=None):
    ts = str(int(ts if ts is not None else time.time()))
    sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
    h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
    if site:
        h[shops.SITE_HEADER] = site
    return h


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class ServiceTest(unittest.TestCase):
    def setUp(self):
        self.shop = FakeTenant()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW)

    def press(self, raw=None, h=None):
        raw = raw or body()
        code, out, _ = self.svc.handle("POST", "/sst/work", signed(raw) if h is None else h, raw)
        return code, json.loads(out)

    def test_s1_a_press_writes_the_rows_of_the_runs_stores_in_the_retailers_order(self):
        code, out = self.press()
        self.assertEqual((code, out["message"]["level"]), (200, "success"))
        ((dt, name, w),) = self.shop.writes
        self.assertEqual((dt, name), (sst.RUN, "SST-00001"))
        self.assertEqual([(r["style"], r["colour"], r["size"], r["store"], r["sold"], r["in_stock"], r["sell_through"],
                           r["none_left"]) for r in w["rows"]],
                         [("DRESS-A", "Red", "S", "Mall - DR", 3, 0, 100.0, 1),
                          ("DRESS-A", "Red", "S", "High Street - DR", 1, 2, 33.3, 0),
                          ("DRESS-A", "Red", "L", "Mall - DR", 1, 4, 20.0, 0),
                          ("DRESS-B", "Black", "M", "Mall - DR", 0, 6, 0.0, 0)])
        self.assertEqual(set(w), {"rows", "summary"})        # no time: Desk shows when, in the site's own time zone
        self.assertEqual(w["summary"], "5 sold since 2026-10-01, 12 in stock now: 29.4% sold through, across 2 stores. "
                                       "1 row sold out: none left in that store.")
        self.assertTrue(out["message"]["body"].startswith("4 rows written. 5 sold"))

    def test_s2_the_reads_name_the_group_the_dates_and_each_store(self):
        self.press()
        reports = sorted(c[1:] for c in self.shop.calls if c[0] == "report")
        pos = {"report_type": "Item", "pos": "", "item_group": "", "item_code": "", "customer": "", "customer_group": "",
               "from_date": "2026-10-01", "to_date": "2026-10-30"}
        self.assertEqual(reports, sorted(
            [(sst.POS_SALE_REPORT, json.dumps(dict(pos, warehouse=s), sort_keys=True)) for s in ("Mall - DR", "High Street - DR")]
            + [(sst.STOCK_REPORT, json.dumps({"warehouse": s, "item_group": "Dresses"}, sort_keys=True))
               for s in ("Mall - DR", "High Street - DR")]))
        (items,) = [c for c in self.shop.calls if c[0] == "rows"]
        self.assertEqual(json.loads(items[2]), [["item_group", "=", "Dresses"], ["variant_of", "is", "set"],
                                                ["disabled", "=", 0]])
        self.assertEqual(items[3], sst.ITEMS_MAX)
        self.assertEqual(sorted(c[2] for c in self.shop.calls if c[:2] == ("doc", "Item Attribute")), ["Colour", "Size"])

    def test_s3_a_named_style_reads_that_style_only(self):
        self.shop.runs["SST-00001"]["style"] = "DRESS-B"
        self.press()
        (items,) = [c for c in self.shop.calls if c[0] == "rows"]
        self.assertIn(["variant_of", "=", "DRESS-B"], json.loads(items[2]))
        self.assertEqual({r["style"] for r in self.shop.writes[0][2]["rows"]}, {"DRESS-B"})

    def test_s4_a_misfilled_run_is_said_in_words_and_reads_nothing_else(self):
        self.shop.runs["SST-00001"]["stores"] = []
        code, out = self.press()
        self.assertEqual((code, out["message"]["level"]), (200, "warning"))
        self.assertIn("add at least one store", out["message"]["body"])
        self.assertEqual(self.shop.calls, [("doc", sst.RUN, "SST-00001")])
        self.assertEqual(self.shop.writes, [])

    def test_s5_the_apps_user_refused_by_the_retailer_is_said_in_words(self):
        self.shop.refuse = 403
        code, out = self.press()
        self.assertEqual((code, out["message"]["body"]), (200, app.REFUSED))
        self.assertEqual(self.shop.writes, [])

    def test_s5b_a_report_refusing_the_apps_user_is_named_in_words(self):
        for code in (417, 403):                 # 417: a right missing on a filter's record type, or the report off
            self.shop.writes = []
            real = FakeTenant.report

            def refusing(name, filters, timeout=None, code=code):
                if name == sst.POS_SALE_REPORT:
                    raise app.ReportRefused(name, code)
                return real(self.shop, name, filters, timeout)
            self.shop.report = refusing
            code_, out = self.press()
            self.assertEqual((code_, out["message"]["body"]), (200, app.REPORT_REFUSED.format(sst.POS_SALE_REPORT)))
            self.assertEqual(self.shop.writes, [])

    def test_s5c_the_door_turns_a_reports_403_and_417_into_a_refusal_and_nothing_else(self):
        t = app.Tenant("https://shop.example", "k", "s")
        for code, refused in ((417, True), (403, True), (404, False), (500, False)):
            def fail(*a, code=code, **k):
                raise app.TenantError("x", code)
            t._open = fail
            with self.assertRaises(app.TenantError) as e:
                t.report(sst.STOCK_REPORT, {})
            self.assertEqual(isinstance(e.exception, app.ReportRefused), refused, code)

    def test_s6_a_press_signed_with_another_secret_or_too_old_is_refused_before_any_read(self):
        raw = body()
        self.assertEqual(self.press(raw, signed(raw, "other"))[0], 401)
        self.assertEqual(self.press(raw, signed(raw, ts=time.time() - 3600))[0], 401)
        self.assertEqual(self.shop.calls, [])

    def test_s7_a_press_on_anything_but_one_run_is_refused_before_any_read(self):
        self.assertEqual(self.press(body(doctype="Item"))[0], 400)
        self.assertEqual(self.press(body(names=("SST-00001", "SST-00002")))[0], 400)
        self.assertEqual(self.shop.calls, [])

    def test_s8_reads_that_take_the_press_time_write_nothing_and_say_so(self):
        clock = Clock()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW, clock=clock)
        real = self.shop.doc

        def slow(doctype, name, timeout=None):
            if doctype == sst.RUN:
                clock.t += 8.0                  # the run's own read takes the press's seven seconds
            return real(doctype, name, timeout)
        self.shop.doc = slow
        code, out = self.press()
        self.assertEqual((code, out["message"]["body"]), (200, app.LATE))
        self.assertEqual(self.shop.calls, [("doc", sst.RUN, "SST-00001")])   # no read is started past the time
        self.assertEqual(self.shop.writes, [])

    def test_s9_too_little_time_left_for_the_save_writes_nothing(self):
        clock = Clock()
        self.svc = app.Service(CONF, tenant=self.shop, now=NOW, clock=clock)
        real = self.shop.report

        def slow(name, filters, timeout=None):
            clock.t += 1.55                     # four reports: 6.2 s, leaving less than the save's one second
            return real(name, filters, timeout)
        self.shop.report = slow
        code, out = self.press()
        self.assertEqual((code, out["message"]["body"]), (200, app.LATE))
        self.assertEqual(self.shop.writes, [])

    def test_s10_more_rows_than_a_run_holds_write_nothing(self):
        many = [spq_row(f"V{i}", "Mall - DR", 1) for i in range(sst.ROWS_MAX + 1)]
        self.shop.items += [{"name": f"V{i}", "variant_of": "DRESS-C", "attribute": "Size", "attribute_value": "M",
                             "item_group": "Dresses", "disabled": 0} for i in range(sst.ROWS_MAX + 1)]
        self.shop.runs["SST-00001"]["colour_attribute"] = ""
        self.shop.stock["Mall - DR"] += many
        self.shop.items = [dict(r) for r in self.shop.items]
        # each V<i> is its own size of DRESS-C only if sizes differ: give each its own size
        for i, r in enumerate(x for x in self.shop.items if x["name"].startswith("V")):
            r["attribute_value"] = f"M{i}"
        code, out = self.press()
        self.assertIn(f"more than the {sst.ROWS_MAX} one run holds", out["message"]["body"])
        self.assertEqual(self.shop.writes, [])

    def test_s11_a_group_with_no_sized_variants_is_said_in_words(self):
        self.shop.runs["SST-00001"]["item_group"] = "Shoes"
        code, out = self.press()
        self.assertIn("the group Shoes has no variants with a Size", out["message"]["body"])
        self.assertEqual(self.shop.writes, [])

    def test_s12_a_report_answered_without_its_columns_writes_nothing(self):
        self.shop.sold["Mall - DR"] = [[1, 2, 3]]
        real = self.shop.report

        def other(name, filters, timeout=None):
            a = real(name, filters, timeout)
            if name == sst.POS_SALE_REPORT:
                a["message"]["columns"] = ["a", "b", "c"]
            return a
        self.shop.report = other
        code, out = self.press()
        self.assertIn("POS Sale Report answered without its item and units columns", out["message"]["body"])
        self.assertEqual(self.shop.writes, [])

    def test_s13_a_run_or_attribute_not_found_is_said_in_words(self):
        self.shop.runs["SST-00001"]["size_attribute"] = "Shoe size"
        code, out = self.press()
        self.assertEqual((code, out["message"]["level"]), (200, "warning"))
        self.assertIn("was not found", out["message"]["body"])
        self.assertEqual(self.shop.writes, [])

    def test_s14_a_group_larger_than_one_run_reads_is_said(self):
        real = self.shop.rows
        self.shop.rows = lambda *a, **k: (real(*a, **k) * 1000)[: sst.ITEMS_MAX]
        code, out = self.press()
        self.assertIn("more items than one run reads", out["message"]["body"])
        self.assertEqual(self.shop.writes, [])

    def test_s15_the_press_reads_side_by_side(self):
        gate = threading.Barrier(4, timeout=3)      # the two stores' four reports, all at once
        real = self.shop.report

        def report(name, filters, timeout=None):
            gate.wait()
            return real(name, filters, timeout)
        self.shop.report = report
        code, out = self.press()
        self.assertEqual((code, out["message"]["level"]), (200, "success"))

    def test_s16_nothing_sold_and_nothing_held_writes_an_empty_run_and_says_so(self):
        self.shop.sold, self.shop.stock = {}, {}
        code, out = self.press()
        ((_, _, w),) = self.shop.writes
        self.assertEqual(w["rows"], [])
        self.assertIn("Nothing sold since 2026-10-01", out["message"]["body"])

    def test_s17_the_service_down_on_the_retailers_side_is_a_502(self):
        def down(*a, **k):
            raise app.TenantError("GET Item -> URLError")
        self.shop.rows = down
        code, out = self.press()
        self.assertEqual(code, 502)
        self.assertEqual(self.shop.writes, [])


class ManyRetailers(unittest.TestCase):
    APP = "ivendnext_sst"

    def setUp(self):
        tmp = tempfile.mkdtemp()
        self.store = shops.FileStore(os.path.join(tmp, "shops.json"))
        for site, n in (("shop-a.ivendnext.com", "a"), ("shop-b.ivendnext.com", "b")):
            self.store.put(site, {"site": site, "url": f"https://{site}", "secrets": {
                f"{self.APP}:sub:work": f"work-{n}", "user:sst@x": f"key-{n}:sec-{n}", "user:Administrator": "adm"}})
        self.store.put("shop-c.ivendnext.com", {"site": "shop-c.ivendnext.com", "url": "https://shop-c.ivendnext.com",
                                                "secrets": {f"{self.APP}:sub:work": "work-c"}})     # no user key yet
        self.doors = {}
        self.svc = app.Service({"IVN_LIBRARY_APP": self.APP, "SST_PREFIX": "IVENDNEXT SST"},
                               store=self.store, tenants=self.door, now=NOW)

    def tearDown(self):
        sst.use_prefix("PP SST")

    def door(self, url, key):
        if url not in self.doors:
            self.doors[url] = FakeTenant()
            self.doors[url].runs = {"SST-00001": run_doc()}
            self.doors[url].key = key
        return self.doors[url]

    def press(self, secret, site):
        raw = body()
        code, out, _ = self.svc.handle("POST", "/sst/work", signed(raw, secret, site=site), raw)
        return code, json.loads(out)

    def test_each_retailer_is_checked_with_its_own_secret_and_written_with_its_own_key_under_the_librarys_prefix(self):
        self.assertEqual(self.press("work-b", "shop-a.ivendnext.com")[0], 401)
        code, out = self.press("work-a", "shop-a.ivendnext.com")
        self.assertEqual(code, 200)
        door = self.doors["https://shop-a.ivendnext.com"]
        self.assertEqual(door.key, "key-a:sec-a")                      # never Administrator's
        self.assertEqual(door.writes[0][0], "IVENDNEXT SST Sell-through")
        self.assertNotIn("https://shop-b.ivendnext.com", self.doors)

    def test_a_press_before_the_key_arrives_is_answered_in_words_and_reads_nothing(self):
        code, out = self.press("work-c", "shop-c.ivendnext.com")
        self.assertEqual((code, out["message"]["body"]), (200, app.NOT_SET_UP))
        self.assertEqual(self.doors, {})

    def test_a_refused_user_is_told_to_connect_again(self):
        self.door("https://shop-a.ivendnext.com", "key-a:sec-a").refuse = 401
        code, out = self.press("work-a", "shop-a.ivendnext.com")
        self.assertEqual(out["message"]["body"], app.REFUSED + app.CONNECT_AGAIN)

    def test_the_function_answers_health_and_a_press(self):
        os.environ.update({"IVN_LIBRARY_APP": self.APP, "SST_PREFIX": "IVENDNEXT SST", "IVN_SHOPS_FILE": self.store.path})
        app._KEPT.clear()
        try:
            r = app.lambda_handler({"httpMethod": "GET", "path": "/health", "headers": {}})
            self.assertEqual((r["statusCode"], json.loads(r["body"])), (200, {"ok": 1}))
            raw = body()
            h = {k.lower(): v for k, v in signed(raw, "work-x", site="shop-a.ivendnext.com").items()}
            r = app.lambda_handler({"httpMethod": "POST", "path": "/sst/work", "headers": h,
                                    "body": base64.b64encode(raw).decode(), "isBase64Encoded": True})
            self.assertEqual(r["statusCode"], 401)
        finally:
            for k in ("IVN_LIBRARY_APP", "SST_PREFIX", "IVN_SHOPS_FILE"):
                os.environ.pop(k, None)
            app._KEPT.clear()
            sst.use_prefix("PP SST")

    def test_the_library_prefix_is_required(self):
        with self.assertRaises(SystemExit):
            app.Service({"IVN_LIBRARY_APP": self.APP}, store=self.store)


class ShopApi(unittest.TestCase):
    def test_a_record_name_is_one_path_segment_and_a_redirect_is_not_followed_and_a_report_is_a_form_post(self):
        import http.server
        seen = []

        class H(http.server.BaseHTTPRequestHandler):
            def _r(self):
                n = int(self.headers.get("Content-Length") or 0)
                seen.append((self.command, self.path, self.headers.get("Content-Type"), self.rfile.read(n).decode()))
                self.send_response(302)
                self.send_header("Location", "https://elsewhere.example/")
                self.end_headers()
            do_GET = do_POST = _r

            def log_message(self, *a):
                pass
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            t = app.Tenant(f"http://127.0.0.1:{srv.server_port}", "k", "s")
            with self.assertRaises(app.TenantError) as e:
                t.doc("PP SST Sell-through", "A/B")
            self.assertEqual(e.exception.code, 302)
            with self.assertRaises(app.TenantError):
                t.report("POS Sale Report", {"warehouse": "Mall - DR"})
            self.assertEqual(seen[0][:2], ("GET", "/api/resource/PP%20SST%20Sell-through/A%2FB"))
            self.assertEqual(seen[1][:3], ("POST", "/api/method/ivendnext_mpos.api.v1.run_report",
                                           "application/x-www-form-urlencoded"))
            self.assertIn("report_name=POS+Sale+Report", seen[1][3])
        finally:
            srv.shutdown()


class TestCall(unittest.TestCase):
    """The test call (``X-iVendNext-Test: 1``, tools/app_template/service/testcall.py) at each signed point route: checked
    exactly as a real call to that route, then answered 200 {"test": "ok", "point": <key>} without the point's handler;
    a route the service does not have is 404."""
    BAD = b"not a call"          # a body the point's handler refuses: a real call with it is never answered 200

    def setUp(self):
        self.svc = app.Service(CONF, tenant=object())
        # route -> (the point's key as the site knows it, its secret)
        self.routes = {"/sst/work": (app.SUB, SECRET)}

    def call(self, path, raw, secret, test=True):
        import base64, hashlib, hmac, time
        ts = str(int(time.time()))
        sig = base64.b64encode(hmac.new(secret.encode(), ts.encode() + b"." + raw, hashlib.sha256).digest()).decode()
        h = {"X-iVendNext-Timestamp": ts, "X-iVendNext-Signature": sig}
        if test:
            h["X-iVendNext-Test"] = "1"
        import json
        code, body, _ = self.svc.handle("POST", path, h, raw)
        return code, json.loads(body)

    def test_a_signed_test_call_is_answered_ok_without_the_handler(self):
        for path, (key, secret) in self.routes.items():
            with self.subTest(path):
                self.assertNotEqual(self.call(path, self.BAD, secret, test=False)[0], 200)   # the handler ran, and refused
                self.assertEqual(self.call(path, self.BAD, secret), (200, {"test": "ok", "point": key}))   # it did not run

    def test_a_mis_signed_test_call_gets_the_real_refusal(self):
        for path in self.routes:
            with self.subTest(path):
                real = self.call(path, self.BAD, "not-the-secret", test=False)
                self.assertEqual(real[0], 401)
                self.assertEqual(self.call(path, self.BAD, "not-the-secret"), real)

    def test_a_signed_test_call_to_a_route_the_service_does_not_have_is_404(self):
        path, (_, secret) = next(iter(self.routes.items()))
        for wrong in ("/point/nothing", path + "/extra", path.rsplit("/", 1)[0] + "/nothing"):
            with self.subTest(wrong):
                self.assertEqual(self.call(wrong, self.BAD, secret)[0], 404)


if __name__ == "__main__":
    unittest.main()
